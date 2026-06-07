from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    TokenError,
    create_access_token,
    create_step_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.user import (
    LoginStep1Result,
    LoginStep2,
    PasswordSet,
    PatternSet,
    PinSet,
    Token,
    Unlock,
    UserCreate,
    UserDetail,
    UserRead,
)
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


_STEP1_TTL_SECONDS = 90


@router.post("/login", response_model=LoginStep1Result)
def login(
    username: str = Form(...),
    password: str = Form(...),
    pin: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> LoginStep1Result:
    """Step 1 of the login flow: username + password + PIN (Hydra-style).

    Returns a short-lived ``challenge_token`` (90 s) when the user has a
    pattern configured — the caller must POST it back to ``/login/pattern``
    with the pattern to obtain the real access token. If the user has no
    pattern yet, the full access token is returned here so they can sign in,
    configure their pattern from inside, and rotate next time.
    """
    user = db.query(User).filter(User.username == username).first()
    if user and auth_guard.is_locked(user):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Cuenta bloqueada temporalmente. Inténtalo de nuevo en "
            f"{auth_guard.lock_remaining_minutes(user)} min.",
        )
    if not user or not verify_password(password, user.password_hash):
        if user:
            auth_guard.register_failure(db, user, action="auth.login_failed",
                                        target="password")
        else:
            audit_log.record(
                db, username=username or "?", action="auth.login_failed",
                detail={"reason": "unknown_user"},
            )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario o contraseña inválidos")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Usuario desactivado")

    # If the account has a PIN configured, demand it on every login. PIN is
    # part of step 1, alongside the password — not a substitute for it.
    if user.pin_hash:
        if not pin or not verify_password(pin, user.pin_hash):
            auth_guard.register_failure(db, user, action="auth.login_failed",
                                        target="pin")
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "PIN incorrecto")

    user.last_login_at = datetime.now(timezone.utc)

    # No pattern set yet → finish the login here so the user can get in and
    # configure the pattern from the panel.
    if not user.pattern_hash:
        auth_guard.register_success(db, user, action="auth.login",
                                    detail={"step": 1, "pattern_required": False})
        return LoginStep1Result(
            step=1, rank=user.rank,
            access_token=create_access_token(user.username),
        )

    # Pattern required → hand out the step-1 challenge. Do NOT clear the
    # failure counter yet; only a finished login clears it.
    audit_log.record(db, username=user.username, action="auth.login_step1",
                     detail={"pattern_required": True})
    db.commit()
    return LoginStep1Result(
        step=1, rank=user.rank,
        challenge_token=create_step_token(user.username, step=1,
                                          expires_seconds=_STEP1_TTL_SECONDS),
        expires_in=_STEP1_TTL_SECONDS,
    )


@router.post("/login/pattern", response_model=Token)
def login_step2(
    body: LoginStep2, db: Session = Depends(get_db)
) -> Token:
    """Step 2: trade the step-1 challenge + the unlock pattern for a JWT."""
    try:
        payload = decode_access_token(body.challenge_token)
    except TokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Reto caducado, vuelve a empezar")
    if payload.get("step") != 1:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token de reto inválido")
    user = db.query(User).filter(User.username == payload.get("sub")).first()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario no válido")
    if auth_guard.is_locked(user):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Cuenta bloqueada. Vuelve a empezar en "
            f"{auth_guard.lock_remaining_minutes(user)} min.",
        )
    if not user.pattern_hash or not verify_password(body.pattern, user.pattern_hash):
        auth_guard.register_failure(db, user, action="auth.login_failed",
                                    target="pattern")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Patrón incorrecto")
    auth_guard.register_success(db, user, action="auth.login",
                                detail={"step": 2})
    return Token(access_token=create_access_token(user.username), rank=user.rank)


@router.get("/me", response_model=UserDetail)
def me(user: User = Depends(get_current_user)) -> UserDetail:
    return user_detail(user)


def _require_current(stored: str | None, current: str | None, label: str) -> None:
    """Anti-keylogger guard: rotating a credential requires presenting the
    current one. Skipped only when the credential is being set for the first
    time (``stored is None``)."""
    if stored is None:
        return
    if not current or not verify_password(current, stored):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"{label} actual incorrecta")


@router.post("/password")
def set_password(
    body: PasswordSet,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _require_current(user.password_hash, body.current_password, "Contraseña")
    user.password_hash = hash_password(body.password)
    db.commit()
    audit_log.record(db, username=user.username, action="auth.password_set")
    return {"ok": True}


@router.post("/pin")
def set_pin(
    body: PinSet,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """El propio usuario configura su PIN. Si ya hay uno, pide el actual."""
    _require_current(user.pin_hash, body.current_pin, "PIN")
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
    """El propio usuario configura su patrón. Si ya hay uno, pide el actual."""
    _require_current(user.pattern_hash, body.current_pattern, "Patrón")
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
        from app.services.seed import DEMO_PATTERN, DEMO_PIN
        data["demo_username"] = settings.demo_admin_username
        data["demo_password"] = settings.demo_admin_password
        data["demo_pin"] = DEMO_PIN
        data["demo_pattern"] = DEMO_PATTERN
    return data
