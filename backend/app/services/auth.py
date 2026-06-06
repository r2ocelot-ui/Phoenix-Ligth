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


def user_detail(user: User) -> UserDetail:
    return UserDetail(
        id=user.id,
        username=user.username,
        email=user.email,
        rank=user.rank,
        activity_points=user.activity_points,
        is_active=user.is_active,
        created_at=user.created_at,
        permissions=sorted(ranks.effective_permissions(user)),
        rank_level=ranks.rank_level(user.rank),
        progression=ranks.promotion_eligibility(user),
    )
