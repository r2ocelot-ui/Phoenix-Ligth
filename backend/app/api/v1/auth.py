from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request, Response, status
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
    LoginStep3,
    PasswordSet,
    PatternSet,
    PinSet,
    Token,
    TotpSetupResult,
    TotpVerify,
    Unlock,
    UserCreate,
    UserDetail,
    UserRead,
)
from app.services import audit_log, auth_guard, device_guard, ip_guard, ranks, totp
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


def _issue_login_token(db, user, response, phoenix_device, ua, ip, step):
    """Paso final del login (compartido por las 3 ventanas): registra el
    dispositivo, pone la cookie, audita el éxito y devuelve el JWT."""
    device_id, is_new = device_guard.touch_device(
        db, user_id=user.id, username=user.username,
        device_id=phoenix_device, user_agent=ua, ip=ip,
    )
    response.set_cookie(
        settings.device_cookie_name, device_id,
        max_age=settings.device_cookie_max_age_days * 86400,
        httponly=True, samesite="lax",
    )
    detail = {"step": step, "ip": ip}
    if is_new:
        detail["new_device"] = True
    auth_guard.register_success(db, user, action="auth.login", detail=detail)
    return LoginStep1Result(
        step=int(step) if str(step).isdigit() else 9,
        rank=user.rank, access_token=create_access_token(user.username),
    )


@router.post("/login", response_model=LoginStep1Result)
def login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    pin: str | None = Form(default=None),
    phoenix_device: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> LoginStep1Result:
    """Step 1 of the login flow: username + password + PIN (Hydra-style).

    Returns a short-lived ``challenge_token`` (90 s) when the user has a
    pattern configured — the caller must POST it back to ``/login/pattern``
    with the pattern to obtain the real access token. If the user has no
    pattern yet, the full access token is returned here so they can sign in,
    configure their pattern from inside, and rotate next time.
    """
    ip = ip_guard.client_ip(request)
    ua = request.headers.get("user-agent")
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
                detail={"reason": "unknown_user", "ip": ip},
            )
        ip_guard.register_failure(db, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario o contraseña inválidos")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Usuario desactivado")

    # If the account has a PIN configured, demand it on every login. PIN is
    # part of step 1, alongside the password — not a substitute for it.
    if user.pin_hash:
        if not pin or not verify_password(pin, user.pin_hash):
            auth_guard.register_failure(db, user, action="auth.login_failed",
                                        target="pin")
            ip_guard.register_failure(db, ip)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "PIN incorrecto")

    user.last_login_at = datetime.now(timezone.utc)
    ip_guard.register_success(ip)

    # Patrón configurado → ventana 2 (patrón). Si no, pero hay 2FA → ventana 3
    # (totp). Si no hay ninguno → login terminado aquí.
    if user.pattern_hash:
        audit_log.record(db, username=user.username, action="auth.login_step1",
                         detail={"next": "pattern", "ip": ip})
        db.commit()
        return LoginStep1Result(
            step=1, rank=user.rank, next_step="pattern",
            challenge_token=create_step_token(user.username, step=1,
                                              expires_seconds=_STEP1_TTL_SECONDS),
            expires_in=_STEP1_TTL_SECONDS,
        )
    if user.totp_enabled:
        db.commit()
        return LoginStep1Result(
            step=1, rank=user.rank, next_step="totp",
            challenge_token=create_step_token(user.username, step=2,
                                              expires_seconds=_STEP1_TTL_SECONDS),
            expires_in=_STEP1_TTL_SECONDS,
        )
    return _issue_login_token(db, user, response, phoenix_device, ua, ip, step="1")


@router.post("/login/pattern", response_model=LoginStep1Result)
def login_step2(
    body: LoginStep2,
    request: Request,
    response: Response,
    phoenix_device: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> LoginStep1Result:
    """Ventana 2: reto del paso 1 + patrón. Si la cuenta tiene 2FA, devuelve
    un nuevo reto para la ventana 3 (código TOTP); si no, emite el JWT."""
    ip = ip_guard.client_ip(request)
    ua = request.headers.get("user-agent")
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
        ip_guard.register_failure(db, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Patrón incorrecto")
    # Patrón correcto. Si hay 2FA → ventana 3; si no, emitir token.
    if user.totp_enabled:
        return LoginStep1Result(
            step=2, rank=user.rank, next_step="totp",
            challenge_token=create_step_token(user.username, step=2,
                                              expires_seconds=_STEP1_TTL_SECONDS),
            expires_in=_STEP1_TTL_SECONDS,
        )
    ip_guard.register_success(ip)
    return _issue_login_token(db, user, response, phoenix_device, ua, ip, step="2")


@router.post("/login/totp", response_model=Token)
def login_step3(
    body: LoginStep3,
    request: Request,
    response: Response,
    phoenix_device: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> Token:
    """Ventana 3: reto (step=2) + código 2FA → JWT."""
    ip = ip_guard.client_ip(request)
    ua = request.headers.get("user-agent")
    try:
        payload = decode_access_token(body.challenge_token)
    except TokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Reto caducado, vuelve a empezar")
    if payload.get("step") != 2:
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
    # Acepta el código de 6 dígitos de la app, o una clave de recuperación
    # (que se consume al usarse, para quien perdió el móvil).
    ok = user.totp_enabled and totp.verify(user.totp_secret, body.totp)
    used_recovery = False
    if not ok and user.totp_enabled:
        match = totp.verify_recovery(list(user.totp_recovery or []), body.totp)
        if match:
            user.totp_recovery = [h for h in user.totp_recovery if h != match]  # consumir
            db.add(user)
            ok = used_recovery = True
    if not ok:
        auth_guard.register_failure(db, user, action="auth.login_failed", target="totp")
        ip_guard.register_failure(db, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Código 2FA o clave de recuperación incorrectos")
    if used_recovery:
        audit_log.record(db, username=user.username, action="auth.totp_recovery_used",
                         detail={"remaining": len(user.totp_recovery or [])})
    ip_guard.register_success(ip)
    res = _issue_login_token(db, user, response, phoenix_device, ua, ip, step="3")
    return Token(access_token=res.access_token, rank=user.rank)


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


@router.post("/totp/setup", response_model=TotpSetupResult)
def totp_setup(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TotpSetupResult:
    """Genera (o regenera, si aún no está confirmado) el secreto TOTP y
    devuelve el secreto + la URI otpauth para escanear/introducir en la app.
    No activa el 2FA todavía: hace falta confirmar un código en /totp/verify."""
    if user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "El 2FA ya está activado. Desactívalo primero para regenerarlo.")
    # Reutiliza el secreto pendiente si ya se generó uno (p.ej. el usuario
    # reabrió el modal): así el QR/clave que ya escaneó sigue siendo válido.
    secret = user.totp_secret or totp.generate_secret()
    codes = totp.generate_recovery_codes()
    user.totp_secret = secret
    user.totp_recovery = [totp.hash_code(c) for c in codes]  # guardamos hashes
    db.commit()
    audit_log.record(db, username=user.username, action="auth.totp_setup")
    return TotpSetupResult(
        secret=secret,
        otpauth_uri=totp.provisioning_uri(secret, user.username),
        recovery_codes=codes,  # claro solo aquí; el usuario debe guardarlas
    )


@router.post("/totp/verify")
def totp_verify(
    body: TotpVerify,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Confirma el primer código y activa el 2FA."""
    if not user.totp_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Primero genera el 2FA en /totp/setup")
    if not totp.verify(user.totp_secret, body.code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Código incorrecto. Revisa la hora del dispositivo.")
    user.totp_enabled = True
    db.commit()
    audit_log.record(db, username=user.username, action="auth.totp_enabled")
    return {"ok": True}


@router.delete("/totp")
def totp_disable(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Desactiva el 2FA y borra el secreto + las claves de recuperación."""
    user.totp_enabled = False
    user.totp_secret = None
    user.totp_recovery = []
    db.commit()
    audit_log.record(db, username=user.username, action="auth.totp_disabled")
    return {"ok": True}


@router.post("/totp/recovery")
def totp_regenerate_recovery(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Regenera las claves de recuperación (invalida las anteriores) y las
    devuelve en claro una sola vez. Requiere tener el 2FA activado."""
    if not user.totp_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Activa antes el 2FA")
    codes = totp.generate_recovery_codes()
    user.totp_recovery = [totp.hash_code(c) for c in codes]
    db.commit()
    audit_log.record(db, username=user.username, action="auth.totp_recovery_regen")
    return {"recovery_codes": codes}


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
