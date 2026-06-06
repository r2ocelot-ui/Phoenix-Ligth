from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.audit import AuditRead
from app.services import ranks
from app.services.auth import require_permission

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditRead])
def list_audit(
    limit: int = Query(100, ge=1, le=500),
    username: str | None = None,
    action: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ranks.P_AUDIT_READ)),
):
    query = db.query(AuditLog).order_by(AuditLog.id.desc())
    if username:
        query = query.filter(AuditLog.username == username)
    if action:
        query = query.filter(AuditLog.action == action)
    return query.limit(limit).all()
