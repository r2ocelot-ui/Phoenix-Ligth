from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cabinet_code: str
    serial: str
    imei: str | None
    model: str | None
    firmware: str | None
    is_active: bool
    registered_at: datetime
    last_seen_at: datetime | None


class DeviceCreate(BaseModel):
    cabinet_code: str = Field(..., min_length=1, max_length=32)
    serial: str = Field(..., min_length=4, max_length=64)
    imei: str | None = Field(default=None, max_length=32)
    model: str | None = Field(default=None, max_length=64)
    firmware: str | None = Field(default=None, max_length=32)
