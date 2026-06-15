from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from sqlalchemy import func

from app.core.database import get_db
from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import (
    AdminPatternSet,
    AdminPinSet,
    PasswordReset,
    PermissionOverride,
    ProfileUpdate,
    RankChange,
    UserCreateAdmin,
    UserDetail,
    UserRead,
)
from app.services import audit_log, ranks, tenancy, totp
from app.services.auth import require_permission, user_detail

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/ranks")
def list_ranks() -> list[dict]:
    """Catálogo de rangos (público) — alimenta los selectores del panel con
    nombre y descripción para que el admin elija con criterio."""
    return [
        {
            "id": rid,
            "label": r["label"],
            "description": r["description"],
            "level": r["level"],
        }
        for rid, r in ranks.RANKS.items()
    ]


def _get(db: Session, user_id: int, actor: User | None = None) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if actor is not None:
        tenancy.ensure_visible(user, actor)
    return user


def _ensure_manageable(actor: User, user: User) -> None:
    """Anti-escalado: solo se pueden resetear las credenciales de un usuario de
    rango ESTRICTAMENTE inferior al del actor — ni de un igual, ni de uno
    superior, ni de uno mismo por esta vía (para eso está el autoservicio en
    ``/auth/*``). Evita que un admin de proyecto secuestre la cuenta del owner."""
    if ranks.rank_level(user.rank) >= ranks.rank_level(actor.rank):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "No puedes gestionar las credenciales de un usuario de tu mismo rango o superior",
        )


@router.get("", response_model=list[UserRead])
def list_users(
    project_id: int | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
):
    q = db.query(User).order_by(User.id)
    q = tenancy.scope_query(q, User, actor, project_id)
    return q.all()


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreateAdmin,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
) -> User:
    """Admin-driven account creation (there is no public self-registration)."""
    if db.query(User).filter(func.lower(User.username) == body.username.lower()).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "El usuario ya existe")
    rank = ranks.canonicalize(body.rank)
    if rank not in ranks.RANKS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Rango desconocido: {body.rank}")
    if ranks.rank_level(rank) > ranks.rank_level(actor.rank):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No puedes crear un usuario de rango superior al tuyo")

    # A non-owner admin pins the new user to their own project automatically;
    # an owner creates "global" users (project_id=None) and assigns later.
    new_project_id = actor.project_id if not tenancy.is_global(actor) else None
    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        pin_hash=hash_password(body.pin) if body.pin else None,
        pattern_hash=hash_password(body.pattern) if body.pattern else None,
        rank=rank,
        project_id=new_project_id,
        project_ids=[new_project_id] if new_project_id is not None else [],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit_log.record(
        db, username=actor.username, action="user.create",
        target=user.username,
        detail={"rank": user.rank, "pin": bool(body.pin), "pattern": bool(body.pattern)},
    )
    return user


@router.post("/{user_id}/password")
def set_password(
    user_id: int,
    body: PasswordReset,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
) -> dict:
    user = _get(db, user_id, actor)
    _ensure_manageable(actor, user)
    user.password_hash = hash_password(body.password)
    db.commit()
    audit_log.record(db, username=actor.username, action="user.password_reset", target=user.username)
    return {"ok": True}


# --- Reseteo de credenciales por admin (PIN / patrón). El 2FA NO se toca:
# solo se pueden regenerar sus claves de recuperación (ver más abajo). ---
@router.post("/{user_id}/pin")
def admin_set_pin(
    user_id: int,
    body: AdminPinSet,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
) -> dict:
    """El admin asigna un PIN nuevo (lo entrega al usuario; este lo rota luego)."""
    user = _get(db, user_id, actor)
    _ensure_manageable(actor, user)
    user.pin_hash = hash_password(body.pin)
    db.commit()
    audit_log.record(db, username=actor.username, action="user.pin_reset", target=user.username)
    return {"ok": True}


@router.delete("/{user_id}/pin")
def admin_clear_pin(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
) -> dict:
    user = _get(db, user_id, actor)
    _ensure_manageable(actor, user)
    user.pin_hash = None
    db.commit()
    audit_log.record(db, username=actor.username, action="user.pin_clear", target=user.username)
    return {"ok": True}


@router.post("/{user_id}/pattern")
def admin_set_pattern(
    user_id: int,
    body: AdminPatternSet,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
) -> dict:
    user = _get(db, user_id, actor)
    _ensure_manageable(actor, user)
    user.pattern_hash = hash_password(body.pattern)
    db.commit()
    audit_log.record(db, username=actor.username, action="user.pattern_reset", target=user.username)
    return {"ok": True}


@router.delete("/{user_id}/pattern")
def admin_clear_pattern(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
) -> dict:
    user = _get(db, user_id, actor)
    _ensure_manageable(actor, user)
    user.pattern_hash = None
    db.commit()
    audit_log.record(db, username=actor.username, action="user.pattern_clear", target=user.username)
    return {"ok": True}


@router.post("/{user_id}/totp/recovery")
def admin_regen_totp_recovery(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
) -> dict:
    """Regenera las claves de recuperación 2FA del usuario (invalida las
    anteriores) y las devuelve en claro UNA sola vez para entregárselas.

    NO desactiva el 2FA (se mantiene el "algo que tienes"). Las claves se
    guardan hasheadas, así que ni el admin puede "verlas": solo regenerarlas.
    Es la salida estándar cuando alguien pierde el móvil y los códigos."""
    user = _get(db, user_id, actor)
    _ensure_manageable(actor, user)
    if not user.totp_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El usuario no tiene 2FA activado")
    codes = totp.generate_recovery_codes()
    user.totp_recovery = [totp.hash_code(c) for c in codes]
    db.commit()
    audit_log.record(db, username=actor.username, action="user.totp_recovery_regen",
                     target=user.username, detail={"count": len(codes)})
    return {"recovery_codes": codes}


@router.get("/{user_id}", response_model=UserDetail)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
) -> UserDetail:
    return user_detail(_get(db, user_id, actor), include_notes=True)


@router.patch("/{user_id}/profile", response_model=UserDetail)
def update_profile(
    user_id: int,
    body: ProfileUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
) -> UserDetail:
    """Edita la ficha del trabajador (datos laborales, contractuales y notas
    internas). PATCH parcial: solo toca los campos enviados. Las notas y el DNI
    son datos sensibles, por eso vive bajo ``user:manage`` y queda auditado."""
    user = _get(db, user_id, actor)
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(user, field, (value or "").strip())
    db.commit()
    db.refresh(user)
    audit_log.record(
        db, username=actor.username, action="user.profile",
        target=user.username, detail={"fields": sorted(data.keys())},
    )
    return user_detail(user, include_notes=True)


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
) -> dict:
    """Borra un usuario. Reglas defensivas:
    - No puedes borrarte a ti mismo (evita quedarse sin admins).
    - No puedes borrar un usuario de rango ≥ al tuyo (anti-escalado).
    - Aplica el filtro de proyecto (un admin de Madrid no borra a Barcelona).
    """
    user = _get(db, user_id, actor)
    if user.id == actor.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No puedes borrarte a ti mismo")
    if ranks.rank_level(user.rank) >= ranks.rank_level(actor.rank):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "No puedes borrar a un usuario de tu mismo rango o superior",
        )
    username = user.username
    db.delete(user)
    db.commit()
    audit_log.record(
        db, username=actor.username, action="user.delete", target=username,
    )
    return {"ok": True}


@router.post("/{user_id}/rank", response_model=UserRead)
def change_rank(
    user_id: int,
    body: RankChange,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
) -> User:
    rank = ranks.canonicalize(body.rank)
    if rank not in ranks.RANKS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown rank: {body.rank}")
    if ranks.rank_level(rank) > ranks.rank_level(actor.rank):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot assign a rank above your own")

    user = _get(db, user_id, actor)
    # Anti-escalado: solo se puede re-rankear a alguien de rango ESTRICTAMENTE
    # inferior (coherente con los resets de credenciales). Sin esto, dos
    # admin_proyecto del mismo proyecto podrían degradarse mutuamente.
    _ensure_manageable(actor, user)
    old = user.rank
    user.rank = rank
    db.commit()
    db.refresh(user)
    audit_log.record(
        db,
        username=actor.username,
        action="user.rank_change",
        target=user.username,
        detail={"from": old, "to": user.rank},
    )
    return user


@router.post("/{user_id}/promote", response_model=UserRead)
def promote(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
) -> User:
    user = _get(db, user_id, actor)
    info = ranks.promotion_eligibility(user)
    if not info.get("next_rank") or not info.get("eligible"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Not eligible for promotion: {info}")
    target = info["next_rank"]
    if ranks.rank_level(target) > ranks.rank_level(actor.rank):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot promote above your own rank")

    old = user.rank
    user.rank = target
    db.commit()
    db.refresh(user)
    audit_log.record(
        db,
        username=actor.username,
        action="user.promote",
        target=user.username,
        detail={"from": old, "to": target},
    )
    return user


@router.post("/{user_id}/permissions", response_model=UserDetail)
def set_permissions(
    user_id: int,
    body: PermissionOverride,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
) -> UserDetail:
    unknown = [
        p
        for p in body.extra_permissions + body.denied_permissions
        if p not in ranks.ALL_PERMISSIONS
    ]
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown permissions: {unknown}")

    user = _get(db, user_id, actor)
    user.extra_permissions = list(body.extra_permissions)
    user.denied_permissions = list(body.denied_permissions)
    db.commit()
    db.refresh(user)
    audit_log.record(
        db,
        username=actor.username,
        action="user.permissions",
        target=user.username,
        detail={"extra": body.extra_permissions, "denied": body.denied_permissions},
    )
    return user_detail(user, include_notes=True)
