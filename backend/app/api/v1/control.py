from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.mqtt_client import bus

router = APIRouter(prefix="/cabinets", tags=["control"])


class RelayCommand(BaseModel):
    state: str = Field(..., pattern="^(on|off)$")


class DimCommand(BaseModel):
    level: int = Field(..., ge=0, le=100)


@router.post("/{cabinet_id}/relay")
async def set_relay(cabinet_id: str, cmd: RelayCommand) -> dict:
    try:
        await bus.publish(f"phoenix/cabinets/{cabinet_id}/cmd/relay", cmd.model_dump())
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    return {"sent": True, "cabinet_id": cabinet_id, "state": cmd.state}


@router.post("/{cabinet_id}/dim")
async def set_dim(cabinet_id: str, cmd: DimCommand) -> dict:
    try:
        await bus.publish(f"phoenix/cabinets/{cabinet_id}/cmd/dim", cmd.model_dump())
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    return {"sent": True, "cabinet_id": cabinet_id, "level": cmd.level}
