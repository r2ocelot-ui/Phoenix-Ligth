"""CRUD for the editable role catalogue.

Reads happen against the in-memory ``ranks.RANKS`` cache; writes go through
this module so the cache is rehydrated atomically after each change.
"""
from sqlalchemy.orm import Session

from app.models.role import Role
from app.services import audit_log, ranks


def seed_default_roles(db: Session) -> None:
    """Populate the ``roles`` table with the built-in 7-tier ladder when empty.

    Idempotent — a second call is a no-op. Only inserts ids that don't already
    exist, so an admin can delete a built-in row (the schema allows it) and a
    restart won't silently re-create it. Custom rows are left alone.
    """
    existing = {r.id for r in db.query(Role).all()}
    for rid in ranks.BUILTIN_RANK_ORDER:
        if rid in existing:
            continue
        default = ranks.DEFAULT_RANKS[rid]
        # The wildcard is encoded by the is_owner flag, not by a stored "*"
        # entry — keeps the JSON column free of magic values.
        perms = sorted(p for p in default["permissions"] if p != ranks.WILDCARD)
        db.add(Role(
            id=rid,
            level=default["level"],
            label=default["label"],
            description=default["description"],
            permissions=perms,
            is_builtin=True,
            is_owner=(rid == "owner"),
        ))
    db.commit()
    ranks.reload_ranks(db)


def list_roles(db: Session) -> list[Role]:
    return db.query(Role).order_by(Role.level).all()


def get_role(db: Session, role_id: str) -> Role | None:
    return db.get(Role, role_id)


def update_role(
    db: Session, role: Role, *,
    label: str | None, description: str | None,
    permissions: list[str] | None, level: int | None,
    actor_username: str,
) -> Role:
    detail: dict = {}
    if label is not None and label != role.label:
        detail["label"] = [role.label, label]
        role.label = label
    if description is not None and description != (role.description or ""):
        detail["description"] = [role.description, description]
        role.description = description
    if permissions is not None and not role.is_owner:
        # Defensive: drop unknown permissions silently rather than 422, so
        # a stale UI doesn't lock the admin out of the editor.
        clean = sorted(p for p in set(permissions) if p in ranks.ALL_PERMISSIONS)
        if clean != sorted(role.permissions or []):
            detail["permissions"] = [list(role.permissions or []), clean]
            role.permissions = clean
    if level is not None and level != role.level and not role.is_owner:
        detail["level"] = [role.level, level]
        role.level = level
    db.commit()
    db.refresh(role)
    if detail:
        audit_log.record(db, username=actor_username, action="role.update",
                         target=role.id, detail=detail)
    ranks.reload_ranks(db)
    return role


def create_role(
    db: Session, *, role_id: str, label: str, description: str,
    permissions: list[str], level: int, actor_username: str,
) -> Role:
    clean = sorted(p for p in set(permissions) if p in ranks.ALL_PERMISSIONS)
    role = Role(
        id=role_id, label=label, description=description,
        permissions=clean, level=level,
        is_builtin=False, is_owner=False,
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    audit_log.record(db, username=actor_username, action="role.create",
                     target=role.id, detail={"level": level,
                                             "permissions": clean})
    ranks.reload_ranks(db)
    return role


def delete_role(db: Session, role: Role, *, actor_username: str) -> None:
    db.delete(role)
    db.commit()
    audit_log.record(db, username=actor_username, action="role.delete",
                     target=role.id)
    ranks.reload_ranks(db)
