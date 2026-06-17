"""Role editor endpoints.

Rules (mirroring docs/DECISIONS.md §2.2):

- Reading the catalogue is gated on ``user:view`` so a Supervisor can see the
  ladder but not change it.
- Editing requires ``role:manage`` (built-in to admin_proyecto and owner).
- An admin can only touch a role whose **level is strictly lower** than their
  own — no rewriting your own role, no editing anything above you.
- An admin can never grant a permission they don't already hold themselves
  (the wildcard ``*`` always satisfies this for an Owner).
- ``owner`` is intentionally protected from edits / deletion: locking the
  only god account out of the system would be a foot-gun.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.schemas.role import (
    PermissionInfo,
    RoleCreate,
    RoleRead,
    RoleUpdate,
)
from app.services import ranks, role_store
from app.services.auth import require_permission

router = APIRouter(prefix="/roles", tags=["roles"])


def _ensure_can_edit(actor: User, *, target_level: int) -> None:
    """Block edits on roles at or above the actor's own level."""
    actor_level = ranks.rank_level(actor.rank)
    if target_level >= actor_level:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Solo puedes editar rangos por debajo del tuyo",
        )


def _ensure_can_grant(actor: User, new_perms: list[str] | None) -> None:
    """Block granting a permission the actor doesn't hold themselves."""
    if new_perms is None:
        return
    own = ranks.effective_permissions(actor)
    if ranks.WILDCARD in own:
        return
    missing = [p for p in new_perms if p not in own]
    if missing:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"No puedes asignar permisos que tú no tienes: {', '.join(missing)}",
        )


@router.get("/permissions", response_model=list[PermissionInfo])
def list_permissions(
    _: User = Depends(require_permission(ranks.P_USER_MANAGE)),
):
    """Catalogue of every permission the system understands, with labels.
    Drives the checklist in the editor."""
    return ranks.PERMISSION_CATALOG


@router.get("", response_model=list[RoleRead])
def list_roles(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ranks.P_USER_MANAGE)),
):
    return role_store.list_roles(db)


@router.get("/{role_id}", response_model=RoleRead)
def get_role(
    role_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ranks.P_USER_MANAGE)),
):
    role = role_store.get_role(db, role_id)
    if not role:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rango no encontrado")
    return role


@router.patch("/{role_id}", response_model=RoleRead)
def update_role(
    role_id: str,
    body: RoleUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_ROLE_MANAGE)),
):
    role = role_store.get_role(db, role_id)
    if not role:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rango no encontrado")
    if role.is_owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "El rango owner no se puede editar")
    _ensure_can_edit(actor, target_level=role.level)
    if body.level is not None:
        _ensure_can_edit(actor, target_level=body.level)
    _ensure_can_grant(actor, body.permissions)
    return role_store.update_role(
        db, role,
        label=body.label, description=body.description,
        permissions=body.permissions, level=body.level,
        actor_username=actor.username,
    )


@router.post("", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
def create_role(
    body: RoleCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_ROLE_MANAGE)),
):
    if role_store.get_role(db, body.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un rango con ese id")
    _ensure_can_edit(actor, target_level=body.level)
    _ensure_can_grant(actor, body.permissions)
    return role_store.create_role(
        db, role_id=body.id, label=body.label, description=body.description,
        permissions=body.permissions, level=body.level,
        actor_username=actor.username,
    )


@router.delete("/{role_id}")
def delete_role(
    role_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_ROLE_MANAGE)),
):
    role = role_store.get_role(db, role_id)
    if not role:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rango no encontrado")
    if role.is_builtin or role.is_owner:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Los rangos por defecto no se pueden borrar (puedes editarlos)",
        )
    _ensure_can_edit(actor, target_level=role.level)
    # Refuse if anyone is still on this rank.
    in_use = db.query(User).filter(User.rank == role_id).count()
    if in_use:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"No se puede borrar: {in_use} usuario(s) tienen este rango.",
        )
    role_store.delete_role(db, role, actor_username=actor.username)
    return {"ok": True}
