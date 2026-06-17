from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PermissionInfo(BaseModel):
    id: str
    label: str
    description: str


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    level: int
    label: str
    description: str
    permissions: list[str]
    is_builtin: bool
    is_owner: bool
    updated_at: datetime


class RoleUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    permissions: list[str] | None = None
    level: int | None = Field(default=None, ge=0, le=99)


class RoleCreate(BaseModel):
    # Lowercase, slug-style; the panel can suggest it from the label.
    id: str = Field(..., pattern=r"^[a-z][a-z0-9_]{1,31}$")
    label: str = Field(..., min_length=1, max_length=64)
    description: str = Field(default="", max_length=255)
    permissions: list[str] = []
    level: int = Field(..., ge=0, le=99)
