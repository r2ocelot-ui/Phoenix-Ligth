from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6)
    email: str | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None
    rank: str
    activity_points: int
    is_active: bool
    created_at: datetime


class UserDetail(UserRead):
    permissions: list[str]
    rank_level: int
    progression: dict


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rank: str


class RankChange(BaseModel):
    rank: str


class PermissionOverride(BaseModel):
    extra_permissions: list[str] = []
    denied_permissions: list[str] = []


class ActiveToggle(BaseModel):
    is_active: bool
