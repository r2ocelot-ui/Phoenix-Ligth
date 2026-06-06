from fastapi import APIRouter, HTTPException

from app.core.mqtt_client import bus

router = APIRouter(prefix="/cabinets", tags=["alarms"])


@router.get("/{cabinet_id}/alarms")
async def list_alarms(cabinet_id: str) -> list[dict]:
    """Currently active alarms — at most one entry per alarm type per cabinet."""
    return list(bus.active_alarms.get(cabinet_id, {}).values())


@router.delete("/{cabinet_id}/alarms")
async def acknowledge_all(cabinet_id: str) -> dict:
    if cabinet_id not in bus.active_alarms:
        raise HTTPException(404, "Unknown cabinet")
    bus.active_alarms[cabinet_id] = {}
    return {"acknowledged": True}
