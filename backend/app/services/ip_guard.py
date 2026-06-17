"""Network-level defence: per-IP rate limiting, banlist and siege mode.

Three layers, ordered cheap-to-expensive:

1. ``check_blocked()`` — fast, O(1) lookup. Called from the dependency on
   every authenticated request. Refuses a request when the caller's IP is
   on the banlist (auto or manual) or when siege mode is on and the IP is
   not whitelisted.
2. ``register_failure()`` — called from /auth/login on a bad credential.
   Keeps a small in-memory window of recent failures per IP; once the
   threshold is crossed, materialises an automatic ban row.
3. ``ban()`` / ``unban()`` / ``list_bans()`` — manual gestion from the
   admin panel, audited.
"""
from collections import deque
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.security import IpBan
from app.services import audit_log

# IP -> deque of failure timestamps inside the rolling window.
_failures: dict[str, deque[datetime]] = {}
# Sentinel IPs used as flags in the IpBan table — keeps the schema simple.
SIEGE_FLAG_IP = "__siege__"
WHITELIST_PREFIX = "wl:"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def client_ip(request: Request) -> str:
    """Best-effort client IP. Respects a single X-Forwarded-For hop so the
    reverse proxy in front of FastAPI (if any) doesn't pin every request to
    127.0.0.1. Production should set this header from a trusted proxy only."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "?"


def _active_ban(db: Session, ip: str) -> IpBan | None:
    now = _now()
    return (
        db.query(IpBan)
        .filter(IpBan.ip == ip)
        .filter(or_(IpBan.expires_at.is_(None), IpBan.expires_at > now))
        .order_by(IpBan.id.desc())
        .first()
    )


def is_banned(db: Session, ip: str) -> IpBan | None:
    return _active_ban(db, ip)


def siege_active(db: Session) -> bool:
    return _active_ban(db, SIEGE_FLAG_IP) is not None


def is_whitelisted(db: Session, ip: str) -> bool:
    return _active_ban(db, WHITELIST_PREFIX + ip) is not None


def check_blocked(db: Session, ip: str) -> tuple[bool, str | None]:
    """Returns (blocked, reason). Used by the dependency."""
    ban = _active_ban(db, ip)
    if ban is not None:
        return True, ban.reason or "IP en banlist"
    if siege_active(db) and not is_whitelisted(db, ip):
        return True, "Modo siege activo — solo IPs autorizadas"
    return False, None


def register_failure(db: Session, ip: str) -> IpBan | None:
    """Record a failed auth attempt and auto-ban if the threshold is crossed."""
    if not settings.lockout_enabled:
        return None  # guard desactivado (pruebas): no auto-ban por IP
    window = timedelta(minutes=settings.ip_ban_window_minutes)
    cutoff = _now() - window
    bucket = _failures.setdefault(ip, deque())
    bucket.append(_now())
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) < settings.ip_ban_failed_threshold:
        return None
    # Threshold crossed — ban and clear the in-memory bucket so we don't
    # double-trigger while the ban is active.
    bucket.clear()
    return ban(
        db, ip,
        reason=f"Auto: {settings.ip_ban_failed_threshold} fallos en "
               f"{settings.ip_ban_window_minutes} min",
        banned_by="auto",
        minutes=settings.ip_ban_duration_minutes,
    )


def register_success(ip: str) -> None:
    """Wipe the in-memory failure bucket for an IP that finally got it right."""
    _failures.pop(ip, None)


def ban(
    db: Session, ip: str, *, reason: str | None, banned_by: str,
    minutes: int | None = None,
) -> IpBan:
    expires = _now() + timedelta(minutes=minutes) if minutes else None
    row = IpBan(ip=ip, reason=reason, banned_by=banned_by, expires_at=expires)
    db.add(row)
    db.commit()
    db.refresh(row)
    audit_log.record(
        db, username=banned_by, action="security.ip_banned",
        target=ip, detail={"reason": reason, "minutes": minutes},
    )
    return row


def unban(db: Session, ip: str, *, by: str) -> int:
    """Remove every active ban for an IP. Returns how many rows were removed."""
    bans = (
        db.query(IpBan)
        .filter(IpBan.ip == ip)
        .filter(or_(IpBan.expires_at.is_(None), IpBan.expires_at > _now()))
        .all()
    )
    for row in bans:
        db.delete(row)
    db.commit()
    if bans:
        audit_log.record(db, username=by, action="security.ip_unbanned", target=ip)
    return len(bans)


def list_bans(db: Session, *, include_expired: bool = False) -> list[IpBan]:
    q = db.query(IpBan).order_by(IpBan.id.desc())
    if not include_expired:
        q = q.filter(or_(IpBan.expires_at.is_(None), IpBan.expires_at > _now()))
    # Hide the sentinel flag rows from the regular list.
    return [b for b in q.all() if b.ip != SIEGE_FLAG_IP
            and not b.ip.startswith(WHITELIST_PREFIX)]


def set_siege(db: Session, *, on: bool, by: str) -> bool:
    """Enable/disable siege mode. Idempotent."""
    existing = _active_ban(db, SIEGE_FLAG_IP)
    if on and not existing:
        ban(db, SIEGE_FLAG_IP, reason="Siege mode flag", banned_by=by, minutes=None)
        audit_log.record(db, username=by, action="security.siege_on")
        return True
    if not on and existing:
        unban(db, SIEGE_FLAG_IP, by=by)
        audit_log.record(db, username=by, action="security.siege_off")
        return True
    return False


def whitelist_add(db: Session, ip: str, *, by: str) -> None:
    """Allow an IP through siege mode (idempotent)."""
    if is_whitelisted(db, ip):
        return
    ban(db, WHITELIST_PREFIX + ip, reason="Whitelist", banned_by=by, minutes=None)
    audit_log.record(db, username=by, action="security.whitelist_add", target=ip)


def whitelist_remove(db: Session, ip: str, *, by: str) -> None:
    unban(db, WHITELIST_PREFIX + ip, by=by)
    audit_log.record(db, username=by, action="security.whitelist_remove", target=ip)


def list_whitelist(db: Session) -> list[str]:
    rows = (
        db.query(IpBan)
        .filter(IpBan.ip.like(WHITELIST_PREFIX + "%"))
        .filter(or_(IpBan.expires_at.is_(None), IpBan.expires_at > _now()))
        .all()
    )
    return [r.ip[len(WHITELIST_PREFIX):] for r in rows]
