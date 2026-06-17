from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.mqtt_client import bus
from app.models.cabinet import Cabinet
from app.models.user import User
from app.services import audit_log, ranks, tenancy
from app.services.auth import require_permission

router = APIRouter(prefix="/cabinets", tags=["alarms"])


def _authorize(db: Session, cabinet_id: str, user: User) -> None:
    """El proyecto manda dónde: las alarmas de un cuadro solo las ve/reconoce
    quien tiene ese cuadro en su scope. 404 si no existe o está fuera."""
    cabinet = db.query(Cabinet).filter(Cabinet.code == cabinet_id).first()
    if cabinet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cuadro no encontrado")
    tenancy.ensure_visible(cabinet, user)


@router.get("/{cabinet_id}/alarms")
def list_alarms(
    cabinet_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(ranks.P_CABINET_READ)),
) -> list[dict]:
    """Currently active alarms — at most one entry per alarm type per cabinet."""
    _authorize(db, cabinet_id, user)
    return list(bus.active_alarms.get(cabinet_id, {}).values())


@router.delete("/{cabinet_id}/alarms")
def acknowledge_all(
    cabinet_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(ranks.P_ALARM_ACK)),
) -> dict:
    """Idempotent: returns 200 even if the cabinet has no alarms stored."""
    _authorize(db, cabinet_id, user)
    cleared = len(bus.active_alarms.get(cabinet_id, {}))
    bus.active_alarms[cabinet_id] = {}
    audit_log.record(
        db, username=user.username, action="alarm.ack", target=cabinet_id,
        detail={"cleared": cleared},
    )
    return {"acknowledged": True, "cleared": cleared}
