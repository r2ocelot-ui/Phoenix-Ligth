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
    has_pin: bool = False
    has_pattern: bool = False


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rank: str


class UserCreateAdmin(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6)
    email: str | None = None
    rank: str = "novato"


class PasswordSet(BaseModel):
    password: str = Field(..., min_length=6)


class PinSet(BaseModel):
    pin: str = Field(..., pattern=r"^\d{4,8}$")


class PatternSet(BaseModel):
    # Sequence of node indices on the 3×3 grid (0–8), 4–9 nodes, each once.
    pattern: str = Field(..., pattern=r"^[0-8]{4,9}$")


class Unlock(BaseModel):
    """Unlock the locked session with whichever credential the user set."""
    pin: str | None = Field(default=None, pattern=r"^\d{4,8}$")
    pattern: str | None = Field(default=None, pattern=r"^[0-8]{4,9}$")


class RankChange(BaseModel):
    rank: str


class PermissionOverride(BaseModel):
    extra_permissions: list[str] = []
    denied_permissions: list[str] = []


class ActiveToggle(BaseModel):
    is_active: bool
