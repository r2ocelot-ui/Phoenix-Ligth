from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.user import Token, UserCreate, UserDetail, UserRead
from app.services import audit_log, ranks
from app.services.auth import get_current_user, user_detail

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(body: UserCreate, db: Session = Depends(get_db)) -> User:
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")

    # The very first account bootstraps as owner; everyone else starts as novato.
    is_first = db.query(User).count() == 0
    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        rank=ranks.BOOTSTRAP_RANK if is_first else ranks.DEFAULT_RANK,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit_log.record(
        db,
        username=user.username,
        action="auth.register",
        detail={"rank": user.rank, "bootstrap": is_first},
    )
    return user


@router.post("/login", response_model=Token)
def login(
    form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> Token:
    user = db.query(User).filter(User.username == form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User disabled")

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    audit_log.record(db, username=user.username, action="auth.login")
    return Token(access_token=create_access_token(user.username), rank=user.rank)


@router.get("/me", response_model=UserDetail)
def me(user: User = Depends(get_current_user)) -> UserDetail:
    return user_detail(user)


@router.get("/info")
def info() -> dict:
    """Public hint for the login screen. Demo credentials are only revealed
    while demo mode is on (turn it off in production)."""
    data = {"app": settings.app_name, "demo_mode": settings.demo_mode}
    if settings.demo_mode:
        data["demo_username"] = settings.demo_admin_username
        data["demo_password"] = settings.demo_admin_password
    return data
