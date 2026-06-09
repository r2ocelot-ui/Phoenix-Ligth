"""Brute-force guard: per-user failed-attempt counter with a temporary lockout.

Shared by login (password) and unlock (PIN/pattern). Each failure bumps a
counter; once it crosses ``auth_max_failed_attempts`` the account is locked for
``auth_lockout_minutes`` (the lockout auto-clears, so it self-heals). Every
failure, lockout and success is written to the audit log, which is what feeds
the admin-only security history.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.services import audit_log


def _now() -> datetime:
    return datetime.now(timezone.utc)


def lock_remaining_seconds(user: User) -> int:
    """Seconds left on an active lockout, or 0 if not locked."""
    locked_until = getattr(user, "locked_until", None)
    if not locked_until:
        return 0
    if locked_until.tzinfo is None:  # SQLite hands back naive datetimes
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    remaining = (locked_until - _now()).total_seconds()
    return int(remaining) if remaining > 0 else 0


def lock_remaining_minutes(user: User) -> int:
    secs = lock_remaining_seconds(user)
    return (secs + 59) // 60  # round up so "0 min" never shows while locked


def is_locked(user: User) -> bool:
    if not settings.lockout_enabled:
        return False
    return lock_remaining_seconds(user) > 0


def register_failure(
    db: Session, user: User, *, action: str, target: str | None = None
) -> None:
    """Record a failed attempt and lock the account if the threshold is hit."""
    user.failed_attempts = (user.failed_attempts or 0) + 1
    # Cuando el guard está desactivado (pruebas) se registra el fallo en la
    # auditoría pero nunca se bloquea la cuenta.
    locked = settings.lockout_enabled and user.failed_attempts >= settings.auth_max_failed_attempts
    if locked:
        user.locked_until = _now() + timedelta(minutes=settings.auth_lockout_minutes)
    db.add(user)
    audit_log.record(
        db, username=user.username, action=action, target=target,
        detail={"failed_attempts": user.failed_attempts, "locked": locked},
    )
    if locked:
        audit_log.record(
            db, username=user.username, action="auth.lockout", target=target,
            detail={"minutes": settings.auth_lockout_minutes},
        )


def register_success(
    db: Session, user: User, *, action: str, detail: dict | None = None
) -> None:
    """Clear the counter on a good credential and log the success."""
    if user.failed_attempts or user.locked_until:
        user.failed_attempts = 0
        user.locked_until = None
    db.add(user)
    audit_log.record(db, username=user.username, action=action, detail=detail)
