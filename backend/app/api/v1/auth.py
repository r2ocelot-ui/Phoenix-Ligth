from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.user import PatternSet, PinSet, Token, Unlock, UserCreate, UserDetail, UserRead
from app.services import audit_log, auth_guard, ranks
from app.services.auth import get_current_user, user_detail

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(body: UserCreate, db: Session = Depends(get_db)) -> User:
    """Bootstrap only. Self-registration is allowed *only* to create the very
    first owner account on an empty system. After that, accounts are created by
    an administrator from the Users section."""
    if db.query(User).count() > 0:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "El registro está deshabilitado. Pide acceso a un administrador.",
        )
    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        rank=ranks.BOOTSTRAP_RANK,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit_log.record(db, username=user.username, action="auth.bootstrap", detail={"rank": user.rank})
    return user


@router.post("/login", response_model=Token)
def login(
    form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> Token:
    user = db.query(User).filter(User.username == form.username).first()
    if user and auth_guard.is_locked(user):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Cuenta bloqueada temporalmente. Inténtalo de nuevo en "
            f"{auth_guard.lock_remaining_minutes(user)} min.",
        )
    if not user or not verify_password(form.password, user.password_hash):
        if user:
            auth_guard.register_failure(db, user, action="auth.login_failed")
        else:
            # Log attempts on unknown usernames too — useful for spotting probes.
            audit_log.record(
                db, username=form.username or "?", action="auth.login_failed",
                detail={"reason": "unknown_user"},
            )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User disabled")

    user.last_login_at = datetime.now(timezone.utc)
    auth_guard.register_success(db, user, action="auth.login")
    return Token(access_token=create_access_token(user.username), rank=user.rank)


@router.get("/me", response_model=UserDetail)
def me(user: User = Depends(get_current_user)) -> UserDetail:
    return user_detail(user)


@router.post("/pin")
def set_pin(
    body: PinSet,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """El propio usuario configura su PIN de desbloqueo rápido."""
    user.pin_hash = hash_password(body.pin)
    db.commit()
    audit_log.record(db, username=user.username, action="auth.pin_set")
    return {"ok": True}


@router.delete("/pin")
def clear_pin(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    user.pin_hash = None
    db.commit()
    audit_log.record(db, username=user.username, action="auth.pin_clear")
    return {"ok": True}


@router.post("/pattern")
def set_pattern(
    body: PatternSet,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """El propio usuario configura su patrón de desbloqueo (3×3, estilo móvil)."""
    user.pattern_hash = hash_password(body.pattern)
    db.commit()
    audit_log.record(db, username=user.username, action="auth.pattern_set")
    return {"ok": True}


@router.delete("/pattern")
def clear_pattern(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    user.pattern_hash = None
    db.commit()
    audit_log.record(db, username=user.username, action="auth.pattern_clear")
    return {"ok": True}


@router.post("/unlock", response_model=Token)
def unlock(
    body: Unlock,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Token:
    """Re-validar la sesión bloqueada con el PIN o el patrón del propio usuario.
    Devuelve un token nuevo (rotación) — la pantalla bloqueada lo guarda.
    Tras demasiados fallos la cuenta se bloquea y obliga a iniciar sesión."""
    if auth_guard.is_locked(user):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Bloqueado por intentos fallidos. Vuelve a iniciar sesión en "
            f"{auth_guard.lock_remaining_minutes(user)} min.",
        )
    method = None
    if body.pin is not None and user.pin_hash and verify_password(body.pin, user.pin_hash):
        method = "pin"
    elif body.pattern is not None and user.pattern_hash and verify_password(
        body.pattern, user.pattern_hash
    ):
        method = "pattern"
    if method is None:
        auth_guard.register_failure(db, user, action="auth.unlock_failed")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credencial incorrecta")
    auth_guard.register_success(db, user, action="auth.unlock", detail={"method": method})
    return Token(access_token=create_access_token(user.username), rank=user.rank)


@router.get("/info")
def info() -> dict:
    """Public hint for the login screen. Demo credentials are only revealed
    while demo mode is on (turn it off in production)."""
    data = {
        "app": settings.app_name,
        "demo_mode": settings.demo_mode,
        "session_idle_minutes": settings.session_idle_minutes,
    }
    if settings.demo_mode:
        data["demo_username"] = settings.demo_admin_username
        data["demo_password"] = settings.demo_admin_password
    return data
