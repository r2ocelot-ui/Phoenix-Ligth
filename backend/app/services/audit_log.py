"""Append-only audit/history recording helper."""
from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def record(
    db: Session,
    *,
    username: str,
    action: str,
    target: str | None = None,
    detail: dict | None = None,
) -> None:
    db.add(AuditLog(username=username, action=action, target=target, detail=detail))
    db.commit()
