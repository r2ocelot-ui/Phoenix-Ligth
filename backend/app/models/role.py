"""Editable role catalogue — moves Phoenix's rank ladder from code into the
database so an Owner or project admin can rebalance "what a Técnico can do"
without a code change.

The 7 default rows are seeded the first time the table is empty. Each role
keeps its ``id`` (the canonical name used everywhere else in the code) but
its ``label``, ``description`` and ``permissions`` are user-editable. The
``is_owner`` flag marks the single role that grants the wildcard — it stays
locked from edits to prevent foot-guns (locking the only admin out of the
system).
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    level: Mapped[int] = mapped_column(Integer, index=True)
    label: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(255), default="")
    # JSON column so the permission set lives in one row — easier to read,
    # easier to edit from the panel, and the catalogue is small enough that
    # a many-to-many would be overkill.
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Built-in rows ship with Phoenix; custom rows are admin-created.
    # Both are editable, but only custom rows can be deleted.
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    # The wildcard role (only one) — protected from edits altogether.
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
