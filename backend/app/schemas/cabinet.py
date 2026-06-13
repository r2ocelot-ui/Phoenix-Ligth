from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Modo de regulación y perfil de vía (ver models/cabinet.py + dimming_controller).
DimmingMode = Literal["manual", "schedule", "ai"]
StreetProfile = Literal["arterial", "residential", "crossing"]


class CabinetCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=32)
    name: str = ""
    number: int = 0
    color: str = "#f97316"
    zone: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    project_id: int | None = None
    street_profile: StreetProfile = "residential"


class CabinetUpdate(BaseModel):
    name: str | None = None
    number: int | None = None
    color: str | None = None
    zone: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    project_id: int | None = None  # mover el cuadro a una ciudad/proyecto
    dimming_mode: DimmingMode | None = None
    street_profile: StreetProfile | None = None


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
    project_id: int | None = None
    dimming_mode: str = "schedule"
    street_profile: str = "residential"
