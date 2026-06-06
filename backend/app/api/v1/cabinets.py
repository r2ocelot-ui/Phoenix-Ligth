from fastapi import APIRouter, Depends, HTTPException, status

from app.core.mqtt_client import bus
from app.models.user import User
from app.services import ranks
from app.services.auth import require_permission

router = APIRouter(prefix="/cabinets", tags=["cabinets"])


@router.get("")
def list_cabinets(
    _: User = Depends(require_permission(ranks.P_CABINET_READ)),
) -> list[dict]:
    """Live snapshot of every known cabinet: telemetry, state and active alarms."""
    return bus.snapshot()


@router.get("/{cabinet_id}/snapshot")
def get_cabinet(
    cabinet_id: str,
    _: User = Depends(require_permission(ranks.P_CABINET_READ)),
) -> dict:
    for cabinet in bus.snapshot():
        if cabinet["cabinet_id"] == cabinet_id:
            return cabinet
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown cabinet")
