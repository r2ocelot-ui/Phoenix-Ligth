"""Known-devices tracking, Google-style.

The first time a user logs in from a browser, ``touch_device()`` issues a
random opaque ID and stores it on the user's device list. Subsequent logins
from the same cookie just update last_seen_at. A login from an unknown
device is left in place but flagged in the audit log so the admin sees it
in the security feed and can flag/revoke it from the panel.
"""
import secrets
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.security import UserDevice
from app.services import audit_log


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def touch_device(
    db: Session, *, user_id: int, username: str,
    device_id: str | None, user_agent: str | None, ip: str | None,
) -> tuple[str, bool]:
    """Look up or create the device row for this user. Returns (device_id, is_new).
    ``is_new`` is True when the cookie was absent or unknown for the user —
    that's the case the admin wants to see in the security feed."""
    if device_id:
        row = (
            db.query(UserDevice)
            .filter(UserDevice.user_id == user_id, UserDevice.device_id == device_id)
            .first()
        )
        if row is not None:
            row.last_seen_at = _utcnow()
            row.last_ip = ip
            if user_agent:
                row.user_agent = user_agent[:255]
            db.add(row)
            db.commit()
            return device_id, False

    new_id = secrets.token_urlsafe(16)
    db.add(UserDevice(
        user_id=user_id, device_id=new_id,
        user_agent=(user_agent or "")[:255] or None,
        last_ip=ip, label=_label_from_ua(user_agent),
    ))
    db.commit()
    audit_log.record(
        db, username=username, action="security.new_device",
        detail={"ip": ip, "user_agent": (user_agent or "")[:120]},
    )
    return new_id, True


def list_devices(db: Session, user_id: int) -> list[UserDevice]:
    return (
        db.query(UserDevice)
        .filter(UserDevice.user_id == user_id)
        .order_by(UserDevice.last_seen_at.desc())
        .all()
    )


def revoke_device(db: Session, *, user_id: int, username: str, device_id: str) -> bool:
    row = (
        db.query(UserDevice)
        .filter(UserDevice.user_id == user_id, UserDevice.device_id == device_id)
        .first()
    )
    if row is None:
        return False
    db.delete(row)
    db.commit()
    audit_log.record(
        db, username=username, action="security.device_revoked",
        detail={"device_id": device_id},
    )
    return True


def _label_from_ua(user_agent: str | None) -> str:
    """Tiny heuristic label so the device list in the panel reads nicely.
    Good enough for "Chrome en Windows" without a UA parser dependency."""
    if not user_agent:
        return "Desconocido"
    ua = user_agent.lower()
    browser = (
        "Edge" if "edg/" in ua else
        "Chrome" if "chrome" in ua and "edg/" not in ua else
        "Firefox" if "firefox" in ua else
        "Safari" if "safari" in ua else
        "Navegador"
    )
    system = (
        "Windows" if "windows" in ua else
        "macOS" if "mac os" in ua or "macintosh" in ua else
        "Linux" if "linux" in ua else
        "iOS" if "iphone" in ua or "ipad" in ua else
        "Android" if "android" in ua else
        "?"
    )
    return f"{browser} en {system}"
