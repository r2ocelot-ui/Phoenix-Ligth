from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    created_at: datetime


class ProjectCreate(BaseModel):
    # Short slug used by the UI (e.g. "madrid", "barcelona").
    code: str = Field(..., min_length=2, max_length=32, pattern=r"^[a-z0-9_\-]+$")
    name: str = Field(..., min_length=2, max_length=128)


class ProjectAssignUser(BaseModel):
    user_id: int
    project_id: int | None  # None = unassign (global)
