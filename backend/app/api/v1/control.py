from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.mqtt_client import bus
from app.models.cabinet import Cabinet
from app.models.user import User
from app.services import audit_log, ranks, tenancy
from app.services.auth import require_permission

router = APIRouter(prefix="/cabinets", tags=["control"])

emergency_router = APIRouter(prefix="/emergency", tags=["control"])


def _authorize_cabinet(db: Session, cabinet_id: str, user: User) -> Cabinet:
    """Devuelve el cuadro si existe y está dentro del proyecto del usuario;
    si no, 404. Cierra el bypass multi-tenant que dejaba que un operario de una
    ciudad enviase comandos a cuadros de otra solo conociendo su ``cabinet_id``."""
    cabinet = db.query(Cabinet).filter(Cabinet.code == cabinet_id).first()
    if cabinet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cuadro no encontrado")
    tenancy.ensure_visible(cabinet, user)
    return cabinet


@emergency_router.post("/all-on")
async def emergency_all_on(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(ranks.P_CABINET_CONTROL)),
) -> dict:
    """Modo emergencia: enciende todo y pone dimming al 100% en cada cuadro
    conocido. Pensado para incidencias (corte de luz, accidente, evento).

    Multi-tenant: solo afecta a los cuadros del proyecto del usuario. Un
    owner sin filtro activo abarca todos."""
    visible = tenancy.cabinet_codes_in_scope(db, user, None)
    affected = []
    for cid in sorted(bus._known_cabinets):
        if visible is not None and cid not in visible:
            continue
        try:
            await bus.publish(f"phoenix/cabinets/{cid}/cmd/relay", {"state": "on"})
            await bus.publish(f"phoenix/cabinets/{cid}/cmd/dim", {"level": 100})
        except RuntimeError:
            pass  # broker no conectado; el estado comandado igual se registra
        bus.record_command(cid, relay="on", dim=100)
        affected.append(cid)
    # En emergencia los cuadros pasan a manual para que el programador no los
    # vuelva a regular hasta que el operario los devuelva a su modo.
    if affected:
        db.query(Cabinet).filter(Cabinet.code.in_(affected)).update(
            {"dimming_mode": "manual"}, synchronize_session=False
        )
        db.commit()
    bus.notify()
    user.activity_points += 5
    db.add(user)
    audit_log.record(
        db, username=user.username, action="emergency.all_on",
        detail={"cabinets": affected},
    )
    return {"ok": True, "cabinets": affected}

ACTIVITY_PER_COMMAND = 1


class RelayCommand(BaseModel):
    state: str = Field(..., pattern="^(on|off)$")


class DimCommand(BaseModel):
    level: int = Field(..., ge=0, le=100)


def _credit_and_audit(
    db: Session, user: User, action: str, target: str, detail: dict
) -> None:
    """Reward activity (feeds rank progression) and write the audit entry.

    SQLite writes are sub-millisecond, so doing this inline on the event loop is
    acceptable for the prototype; move to a background task for high throughput.
    """
    user.activity_points += ACTIVITY_PER_COMMAND
    ranks.maybe_auto_promote(
        user,
        enabled=settings.auto_promote_enabled,
        max_rank=settings.auto_promote_max_rank,
    )
    db.add(user)
    audit_log.record(db, username=user.username, action=action, target=target, detail=detail)


@router.post("/{cabinet_id}/relay")
async def set_relay(
    cabinet_id: str,
    cmd: RelayCommand,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(ranks.P_CABINET_CONTROL)),
) -> dict:
    _authorize_cabinet(db, cabinet_id, user)
    try:
        await bus.publish(f"phoenix/cabinets/{cabinet_id}/cmd/relay", cmd.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    bus.record_command(cabinet_id, relay=cmd.state)
    bus.notify()
    _credit_and_audit(db, user, "cabinet.relay", cabinet_id, {"state": cmd.state})
    return {"sent": True, "cabinet_id": cabinet_id, "state": cmd.state}


@router.post("/{cabinet_id}/dim")
async def set_dim(
    cabinet_id: str,
    cmd: DimCommand,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(ranks.P_CABINET_CONTROL)),
) -> dict:
    cabinet = _authorize_cabinet(db, cabinet_id, user)
    try:
        await bus.publish(f"phoenix/cabinets/{cabinet_id}/cmd/dim", cmd.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    bus.record_command(cabinet_id, dim=cmd.level)
    # Mover el slider = tomar control manual: el programador deja de tocarlo
    # hasta que se devuelva a programa/IA desde el selector de modo.
    if cabinet.dimming_mode != "manual":
        cabinet.dimming_mode = "manual"
        db.add(cabinet)
    bus.notify()
    _credit_and_audit(db, user, "cabinet.dim", cabinet_id, {"level": cmd.level})
    return {"sent": True, "cabinet_id": cabinet_id, "level": cmd.level, "mode": "manual"}


class ModeCommand(BaseModel):
    mode: Literal["manual", "schedule", "ai"]


@router.post("/{cabinet_id}/mode")
async def set_mode(
    cabinet_id: str,
    cmd: ModeCommand,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(ranks.P_CABINET_CONTROL)),
) -> dict:
    """Cambia el modo de regulación del cuadro:
      - ``manual``   → el operario manda; el programador no lo toca.
      - ``schedule`` → programa horario fijo (+ lux).
      - ``ai``       → motor adaptativo: sol + tarifa + lux + perfil de calle.

    En modo automático (schedule/ai) aplica YA el nivel calculado para dar
    feedback inmediato, sin esperar al siguiente ciclo del programador."""
    cabinet = _authorize_cabinet(db, cabinet_id, user)
    cabinet.dimming_mode = cmd.mode
    db.add(cabinet)
    db.commit()
    db.refresh(cabinet)
    level = None
    if cmd.mode != "manual":
        level = await bus.apply_level_now(cabinet)
    bus.notify()
    _credit_and_audit(db, user, "cabinet.mode", cabinet_id, {"mode": cmd.mode})
    return {"ok": True, "cabinet_id": cabinet_id, "mode": cmd.mode, "level": level}
