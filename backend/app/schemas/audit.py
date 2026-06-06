from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    username: str
    action: str
    target: str | None
    detail: dict | None
