from pydantic import BaseModel, ConfigDict, Field


class CabinetCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=32)
    name: str = ""
    number: int = 0
    color: str = "#f97316"
    zone: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class CabinetUpdate(BaseModel):
    name: str | None = None
    number: int | None = None
    color: str | None = None
    zone: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class CabinetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    number: int
    color: str
    zone: str | None
    latitude: float | None
    longitude: float | None
