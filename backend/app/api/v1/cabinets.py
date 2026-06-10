from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.mqtt_client import bus
from app.models.cabinet import Cabinet
from app.models.user import User
from app.schemas.cabinet import CabinetCreate, CabinetRead, CabinetUpdate
from app.services import audit_log, ranks, sun, tenancy
from app.services.auth import get_current_user, require_permission

router = APIRouter(prefix="/cabinets", tags=["cabinets"])


def _merged(db: Session, visible_codes: set[str] | None) -> list[dict]:
    """Combine live telemetry (from the bus) with registry metadata (from DB).
    ``visible_codes`` filters the result to the caller's project scope; pass
    ``None`` to skip the filter (owner without an active project filter)."""
    live = {c["cabinet_id"]: c for c in bus.snapshot()}
    registry = {c.code: c for c in db.query(Cabinet).all()}
    out = []
    for code in sorted(set(live) | set(registry)):
        if visible_codes is not None and code not in visible_codes:
            continue
        item = live.get(code) or {
            "cabinet_id": code,
            "online": False,
            "status": "ok",
            "telemetry": None,
            "state": {"relay": "on", "dim": 100},
            "alarms": [],
        }
        reg = registry.get(code)
        item["name"] = reg.name if reg else code
        item["number"] = reg.number if reg else 0
        item["color"] = reg.color if reg else "#f97316"
        item["zone"] = reg.zone if reg else None
        item["latitude"] = reg.latitude if reg else None
        item["longitude"] = reg.longitude if reg else None
        item["project_id"] = reg.project_id if reg else None
        out.append(item)
    return out


@router.get("")
def list_cabinets(
    project_id: int | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_READ)),
) -> list[dict]:
    """Live snapshot of every cabinet: telemetry, state, alarms and location."""
    codes = tenancy.cabinet_codes_in_scope(db, actor, project_id)
    return _merged(db, codes)


@router.get("/registry", response_model=list[CabinetRead])
def list_registry(
    project_id: int | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_READ)),
):
    q = db.query(Cabinet).order_by(Cabinet.code)
    q = tenancy.scope_query(q, Cabinet, actor, project_id)
    return q.all()


@router.get("/{cabinet_id}/sun")
def cabinet_sun(
    cabinet_id: str,
    date: str | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_READ)),
) -> dict:
    """Salida/puesta del sol astronómicas para la posición del CM. Offline,
    sin depender de internet. Pensado como red de seguridad de la
    fotocélula: si el sensor lux falla o discrepa de estos valores, hay
    motivo para sospechar de él."""
    from datetime import date as _date
    cabinet = db.query(Cabinet).filter(Cabinet.code == cabinet_id).first()
    if cabinet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cuadro no encontrado")
    tenancy.ensure_visible(cabinet, actor)
    if cabinet.latitude is None or cabinet.longitude is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "El cuadro no tiene coordenadas configuradas")
    target = _date.fromisoformat(date) if date else _date.today()
    sr = sun.sunrise_utc(target, cabinet.latitude, cabinet.longitude)
    ss = sun.sunset_utc(target, cabinet.latitude, cabinet.longitude)
    return {
        "cabinet_id": cabinet.code,
        "date": target.isoformat(),
        "latitude": cabinet.latitude,
        "longitude": cabinet.longitude,
        "sunrise_utc": sr.isoformat() if sr else None,
        "sunset_utc": ss.isoformat() if ss else None,
    }


@router.post("/registry", response_model=CabinetRead, status_code=status.HTTP_201_CREATED)
def create_cabinet(
    body: CabinetCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_MANAGE)),
) -> Cabinet:
    if db.query(Cabinet).filter(Cabinet.code == body.code).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Cabinet code already exists")
    payload = body.model_dump()
    # A non-owner pins the new cabinet to their own project. Owner stays
    # global by default (can move it to a project from the Projects panel).
    if not tenancy.is_global(actor):
        payload["project_id"] = actor.project_id
    cabinet = Cabinet(**payload)
    db.add(cabinet)
    db.commit()
    db.refresh(cabinet)
    audit_log.record(
        db, username=actor.username, action="cabinet.create", target=cabinet.code,
        detail=body.model_dump(),
    )
    return cabinet


@router.patch("/registry/{code}", response_model=CabinetRead)
def update_cabinet(
    code: str,
    body: CabinetUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_MANAGE)),
) -> Cabinet:
    cabinet = db.query(Cabinet).filter(Cabinet.code == code).first()
    if not cabinet:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cabinet not found")
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(cabinet, key, value)
    db.commit()
    db.refresh(cabinet)
    audit_log.record(
        db, username=actor.username, action="cabinet.update", target=code, detail=data
    )
    return cabinet


@router.post("/registry/wipe-all")
def wipe_topology(
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_MANAGE)),
) -> dict:
    """Owner-only nuclear option: drop every cabinet, circuit and light
    point in the database. Useful to start from a blank slate after the
    demo seed. Devices and audit entries are preserved (audit by design)."""
    if not tenancy.is_global(actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Solo el owner puede vaciar la topología completa")
    from app.models.circuit import Circuit
    from app.models.lightpoint import LightPoint
    n_pts = db.query(LightPoint).delete(synchronize_session=False)
    n_circs = db.query(Circuit).delete(synchronize_session=False)
    n_cabs = db.query(Cabinet).delete(synchronize_session=False)
    db.commit()
    # Drop in-memory live state too — otherwise the deleted cabinets keep
    # showing up as offline ghosts in /cabinets until the next restart.
    bus._known_cabinets.clear()
    bus.last_telemetry.clear()
    bus.cabinet_state.clear()
    bus.active_alarms.clear()
    bus.last_lux.clear()
    audit_log.record(
        db, username=actor.username, action="topology.wipe",
        detail={"cabinets": n_cabs, "circuits": n_circs, "points": n_pts},
    )
    return {"cabinets": n_cabs, "circuits": n_circs, "points": n_pts}


@router.delete("/registry/{code}")
def delete_cabinet(
    code: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_MANAGE)),
) -> dict:
    """Delete a cabinet plus everything attached: circuits, light points and
    its in-memory live state. Audited."""
    cabinet = db.query(Cabinet).filter(Cabinet.code == code).first()
    if not cabinet:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cabinet not found")
    tenancy.ensure_visible(cabinet, actor)
    from app.models.circuit import Circuit
    from app.models.lightpoint import LightPoint
    n_pts = db.query(LightPoint).filter(LightPoint.cabinet_code == code).delete()
    n_circs = db.query(Circuit).filter(Circuit.cabinet_code == code).delete()
    db.delete(cabinet)
    db.commit()
    bus._known_cabinets.discard(code)
    bus.last_telemetry.pop(code, None)
    bus.cabinet_state.pop(code, None)
    bus.active_alarms.pop(code, None)
    bus.last_lux.pop(code, None)
    audit_log.record(
        db, username=actor.username, action="cabinet.delete", target=code,
        detail={"circuits": n_circs, "points": n_pts},
    )
    return {"deleted": True, "circuits": n_circs, "points": n_pts}


@router.get("/{cabinet_id}/snapshot")
def get_cabinet(
    cabinet_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ranks.P_CABINET_READ)),
) -> dict:
    for cabinet in _merged(db):
        if cabinet["cabinet_id"] == cabinet_id:
            return cabinet
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown cabinet")
