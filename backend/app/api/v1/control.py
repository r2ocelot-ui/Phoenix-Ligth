from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.mqtt_client import bus
from app.models.user import User
from app.services import audit_log, ranks
from app.services.auth import require_permission

router = APIRouter(prefix="/cabinets", tags=["control"])

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
    try:
        await bus.publish(f"phoenix/cabinets/{cabinet_id}/cmd/dim", cmd.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    bus.record_command(cabinet_id, dim=cmd.level)
    bus.notify()
    _credit_and_audit(db, user, "cabinet.dim", cabinet_id, {"level": cmd.level})
    return {"sent": True, "cabinet_id": cabinet_id, "level": cmd.level}
