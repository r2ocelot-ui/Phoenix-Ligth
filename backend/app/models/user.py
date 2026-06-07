from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # Quick-unlock credentials (hashed like the password). Optional, per user.
    pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pattern_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Brute-force guard: consecutive failures and an auto-expiring lockout.
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rank: Mapped[str] = mapped_column(String(32), default="visualizador")
    # Multi-tenant scaffolding (see docs/DECISIONS.md §3.1). NULL = global,
    # which is the default until proper tenant scoping is wired up.
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Per-user permission overrides on top of the rank defaults.
    extra_permissions: Mapped[list] = mapped_column(JSON, default=list)
    denied_permissions: Mapped[list] = mapped_column(JSON, default=list)
    activity_points: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
