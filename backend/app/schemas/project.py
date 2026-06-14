from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    created_at: datetime
    # Topes de dimming por tramo tarifario propios del proyecto (NULL → usa
    # el default global de settings). Expuestos para que la UI distinga
    # "personalizado" de "por defecto".
    tariff_cap_punta: int | None = None
    tariff_cap_llano: int | None = None
    tariff_cap_valle: int | None = None
    tariff_floor_level: int | None = None
    tariff_enabled: bool | None = None


class ProjectTariffUpdate(BaseModel):
    """Topes de tarifa por proyecto. Cada campo es opcional; ``None`` = "usa el
    global". Solo `0–100` (0 = apaga en ese tramo). El alumbrado nunca se apaga
    por tarifa: el floor protege el dimming, no el on/off. ``tariff_enabled``:
    None=global, False=esta ciudad nunca recorta por precio, True=sí."""
    tariff_cap_punta: int | None = Field(default=None, ge=0, le=100)
    tariff_cap_llano: int | None = Field(default=None, ge=0, le=100)
    tariff_cap_valle: int | None = Field(default=None, ge=0, le=100)
    tariff_floor_level: int | None = Field(default=None, ge=0, le=100)
    tariff_enabled: bool | None = None


class ProjectCreate(BaseModel):
    # Short slug used by the UI (e.g. "madrid", "barcelona").
    code: str = Field(..., min_length=2, max_length=32, pattern=r"^[a-z0-9_\-]+$")
    name: str = Field(..., min_length=2, max_length=128)


class ProjectAssignUser(BaseModel):
    user_id: int
    # Multi-proyecto: lista completa que REEMPLAZA la asignación. Si se omite,
    # se acepta el ``project_id`` único (compatibilidad). Lista vacía o
    # ``project_id=None`` = sin proyecto (global).
    project_ids: list[int] | None = None
    project_id: int | None = None
