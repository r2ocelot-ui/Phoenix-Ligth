from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class IpBanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ip: str
    reason: str | None
    banned_by: str
    banned_at: datetime
    expires_at: datetime | None


class IpBanCreate(BaseModel):
    ip: str = Field(..., min_length=2, max_length=64)
    reason: str | None = Field(default=None, max_length=255)
    minutes: int | None = Field(default=None, ge=1, le=60 * 24 * 365)


class WhitelistAdd(BaseModel):
    ip: str = Field(..., min_length=2, max_length=64)


class SiegeToggle(BaseModel):
    on: bool


class DeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_id: str
    user_agent: str | None
    last_ip: str | None
    label: str | None
    trusted: bool
    first_seen_at: datetime
    last_seen_at: datetime
