from datetime import datetime, timezone
from pydantic import BaseModel, Field


class Measurement(BaseModel):
    cabinet_id: str = Field(..., examples=["CAB-001"])
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Edge timestamp; defaults to server receive time if omitted.",
    )
    voltage_v: float = Field(..., ge=0, description="RMS voltage in volts")
    current_a: float = Field(..., ge=0, description="RMS current in amperes")
    active_power_w: float = Field(..., ge=0)
    power_factor: float = Field(..., ge=0, le=1)
    lamp_circuit: str = Field("L1", description="Circuit identifier (L1/L2/L3)")
