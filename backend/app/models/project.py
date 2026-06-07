"""Project / city model — multi-tenant scaffolding.

The schema includes it so users, cabinets and audit entries can later be
scoped to a specific project without a schema migration. The API does NOT
filter by project_id yet: that switch flips when a second tenant arrives.
See docs/DECISIONS.md §3.1.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
