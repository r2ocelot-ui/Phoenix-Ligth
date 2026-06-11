"""Authentication dependencies for FastAPI.

`get_current_user` decodes the bearer token and loads the user from the DB
(so rank/permission changes take effect immediately, without re-login).
`require_permission` is a dependency factory that gates an endpoint on a
single permission.
"""
from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import TokenError, decode_access_token
from app.models.user import User
from app.schemas.user import UserDetail
from app.services import ranks

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    cred_exc = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
    except TokenError:
        raise cred_exc
    user = db.query(User).filter(User.username == payload.get("sub")).first()
    if user is None:
        raise cred_exc
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User disabled")
    return user


def require_permission(permission: str) -> Callable[..., User]:
    def checker(user: User = Depends(get_current_user)) -> User:
        if not ranks.has_permission(user, permission):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Missing permission: {permission}"
            )
        return user

    return checker


def user_detail(user: User, *, include_notes: bool = False) -> UserDetail:
    """Build the rich user view. ``include_notes`` gates the internal admin
    notes: only callers acting with ``user:manage`` should pass ``True`` —
    ``/auth/me`` leaves it ``False`` so a user never reads notes about himself."""
    return UserDetail(
        id=user.id,
        username=user.username,
        email=user.email,
        rank=user.rank,
        activity_points=user.activity_points,
        is_active=user.is_active,
        created_at=user.created_at,
        project_id=user.project_id,
        permissions=sorted(ranks.effective_permissions(user)),
        rank_level=ranks.rank_level(user.rank),
        progression=ranks.promotion_eligibility(user),
        has_pin=bool(getattr(user, "pin_hash", None)),
        has_pattern=bool(getattr(user, "pattern_hash", None)),
        has_totp=bool(getattr(user, "totp_enabled", False)),
        totp_recovery_remaining=len(getattr(user, "totp_recovery", None) or []),
        # Ficha del trabajador
        full_name=user.full_name or "",
        phone=user.phone or "",
        job_title=user.job_title or "",
        department=user.department or "",
        site=user.site or "",
        shift=user.shift or "",
        employee_id=user.employee_id or "",
        national_id=user.national_id or "",
        company=user.company or "",
        last_login_at=user.last_login_at,
        last_login_ip=user.last_login_ip or "",
        notes=(user.notes or "") if include_notes else None,
    )
