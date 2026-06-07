from pydantic import BaseModel, ConfigDict, Field


class CircuitCreate(BaseModel):
    cabinet_code: str
    number: int = 1
    name: str = ""
    color: str = "#38bdf8"
    phase: str = "III"
    expected_power_w: float = Field(0.0, ge=0)


class CircuitUpdate(BaseModel):
    number: int | None = None
    name: str | None = None
    color: str | None = None
    phase: str | None = None
    expected_power_w: float | None = Field(default=None, ge=0)


class CircuitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cabinet_code: str
    number: int
    name: str
    color: str
    phase: str
    expected_power_w: float = 0.0


class LightPointCreate(BaseModel):
    cabinet_code: str
    circuit_id: int
    number: int = 1
    label: str = ""
    phase: str = "L1"
    latitude: float | None = None
    longitude: float | None = None
    power_w: float = Field(100.0, ge=0)


class LightPointUpdate(BaseModel):
    circuit_id: int | None = None
    number: int | None = None
    label: str | None = None
    phase: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    power_w: float | None = None


class LightPointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cabinet_code: str
    circuit_id: int
    number: int
    label: str
    phase: str
    latitude: float | None
    longitude: float | None
    power_w: float
