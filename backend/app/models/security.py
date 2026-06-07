"""Active-defence models: IP banlist and known user devices.

- IpBan stores network-level blocks (fail2ban-style and manual). The expiry
  is optional: NULL means a permanent ban. Idempotent on (ip, banned_at).
- UserDevice tracks the device fingerprints a user has logged in from. A
  fresh login from an unknown fingerprint is flagged as a security event.

Both are append-only at the API boundary (no UPDATE endpoints): bans are
created/deleted, devices are registered/revoked.
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IpBan(Base):
    __tablename__ = "ip_bans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ip: Mapped[str] = mapped_column(String(64), index=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    banned_by: Mapped[str] = mapped_column(String(64))  # username or "auto"
    banned_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    # NULL = permanent ban. Otherwise the dependency lets it lapse on its own.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UserDevice(Base):
    __tablename__ = "user_devices"
    __table_args__ = (UniqueConstraint("user_id", "device_id", name="uq_user_device"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    fingerprint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trusted: Mapped[bool] = mapped_column(Boolean, default=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
