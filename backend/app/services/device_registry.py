"""Device registry — the SICE-style hardware binding.

Every physical cabinet should be paired with a controller. The MQTT bus
consults ``allow_telemetry()`` before ingesting; telemetry whose serial is
not registered for the expected cabinet is rejected and logged.

Telemetry payloads must include a ``device_serial`` field for enforcement
to apply. Payloads without one (e.g. the demo loop) are accepted to keep
backwards compatibility — flip ``PHOENIX_REQUIRE_DEVICE_SERIAL=true`` to
make it strict.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.device import Device
from app.services import audit_log


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_device_for_cabinet(db: Session, cabinet_code: str) -> Device | None:
    return (
        db.query(Device)
        .filter(Device.cabinet_code == cabinet_code, Device.is_active.is_(True))
        .first()
    )


def allow_telemetry(
    cabinet_code: str, serial: str | None, *, strict: bool,
) -> tuple[bool, str]:
    """Decide whether a telemetry message is accepted. Returns (ok, reason).

    - When the cabinet has no registered device: accepted with reason "unbound"
      if not strict, refused otherwise.
    - When a registered device exists and the serial matches: accepted, the
      device's last_seen_at is bumped.
    - Any mismatch is refused and the impostor logged as a security event.
    """
    with SessionLocal() as db:
        device = get_device_for_cabinet(db, cabinet_code)
        if device is None:
            if strict and serial:
                audit_log.record(
                    db, username="system", action="security.device_unknown",
                    target=cabinet_code, detail={"serial": serial},
                )
                return False, "unbound_strict"
            return True, "unbound"

        if not serial:
            if strict:
                return False, "missing_serial"
            return True, "legacy"

        if serial != device.serial:
            audit_log.record(
                db, username="system", action="security.device_mismatch",
                target=cabinet_code,
                detail={"expected": device.serial, "got": serial},
            )
            return False, "mismatch"

        device.last_seen_at = _utcnow()
        db.add(device)
        db.commit()
        return True, "ok"
