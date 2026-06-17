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
    ambient_lux: float | None = Field(
        None, ge=0, description="Optional ambient light reading; feeds the dimming scheduler."
    )
    # Infrastructure sensors common to a real EMS cabinet.
    cabinet_temp_c: float | None = Field(
        None, ge=-40, le=120,
        description="Internal cabinet temperature in °C (NTC/thermistor).",
    )
    door_open: bool | None = Field(
        None, description="True if the cabinet door is open (reed switch / hall sensor).",
    )
    intrusion: bool | None = Field(
        None, description="True if the tamper/intrusion sensor tripped.",
    )
    device_serial: str | None = Field(
        None, max_length=64,
        description="Serial of the field device emitting this telemetry. "
        "When the cabinet is bound (see /devices) the bus enforces it.",
    )
