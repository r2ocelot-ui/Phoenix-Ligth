from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.mqtt_client import bus
from app.models.user import User
from app.services import audit_log, ranks
from app.services.auth import require_permission

router = APIRouter(prefix="/cabinets", tags=["alarms"])


@router.get("/{cabinet_id}/alarms")
def list_alarms(
    cabinet_id: str,
    _: User = Depends(require_permission(ranks.P_CABINET_READ)),
) -> list[dict]:
    """Currently active alarms — at most one entry per alarm type per cabinet."""
    return list(bus.active_alarms.get(cabinet_id, {}).values())


@router.delete("/{cabinet_id}/alarms")
def acknowledge_all(
    cabinet_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(ranks.P_ALARM_ACK)),
) -> dict:
    """Idempotent: returns 200 even if the cabinet has no alarms stored."""
    cleared = len(bus.active_alarms.get(cabinet_id, {}))
    bus.active_alarms[cabinet_id] = {}
    audit_log.record(
        db, username=user.username, action="alarm.ack", target=cabinet_id,
        detail={"cleared": cleared},
    )
    return {"acknowledged": True, "cleared": cleared}
