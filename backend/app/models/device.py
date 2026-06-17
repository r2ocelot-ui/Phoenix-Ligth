"""Field device registry — the SICE-style hardware binding.

Each physical cabinet has a controller (ESP32 / PLC / RTU) with a unique
serial. Optionally a 4G modem with an IMEI. The MQTT bus only accepts
telemetry that carries a serial matching a registered, active device; any
mismatch is logged as a security event and rejected.

A device is bound to a single cabinet at a time. Rebinding (e.g. controller
replacement) is an explicit operation that creates a new row and deactivates
the previous one — the audit log keeps the trail.
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("serial", name="uq_device_serial"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cabinet_code: Mapped[str] = mapped_column(String(32), index=True)
    serial: Mapped[str] = mapped_column(String(64), index=True)
    imei: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    firmware: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Shared secret the device uses to sign its telemetry. NULL during
    # registration; assigned once and only fetched in /devices/{id}/secret.
    secret_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
