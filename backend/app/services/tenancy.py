"""Project / city scope helpers.

The multi-tenant rules (see docs/DECISIONS.md §3.1):

- An ``owner`` (wildcard permission) sees everything regardless of
  ``project_id`` — they may also pass an explicit ``?project_id=X`` query
  to narrow the view manually (the "Ciudad activa" selector).
- Every other user is locked to their ``user.project_id``:
    * If ``user.project_id`` is set, they see only rows with the same value.
    * If ``user.project_id`` is NULL they're treated as "global" and see
      only rows whose ``project_id`` is also NULL — they never bleed across
      another project.

Apply with ``scope_query(query, model, user, override_id)`` when listing
or ``ensure_visible(row, user)`` when fetching a single resource.
"""
from typing import Iterable

from fastapi import HTTPException, status
from sqlalchemy.orm import Query

from app.models.user import User
from app.services import ranks


def is_global(user: User) -> bool:
    """Owners (wildcard) cross project boundaries by design."""
    return ranks.WILDCARD in ranks.effective_permissions(user)


def scoped_project_ids(user: User, override_project_id: int | None = None) -> set[int] | None:
    """Conjunto de project_ids que el usuario puede ver, o ``None`` si es owner
    sin filtro (ve todo).

    - Owner: ``{override}`` si pasa una ciudad activa, si no ``None`` (todo).
    - Resto: la unión de ``project_ids`` (multi-proyecto) y el ``project_id``
      principal. Un set **vacío** significa "solo recursos globales" (sin
      proyecto), conservando el comportamiento anterior.
    """
    if is_global(user):
        return {override_project_id} if override_project_id is not None else None
    ids = set(user.project_ids or [])
    if user.project_id is not None:
        ids.add(user.project_id)
    return ids


def scope_query(query: Query, model, user: User, override_project_id: int | None = None) -> Query:
    """Apply the project filter to a SQLAlchemy query against ``model``.
    ``model`` must expose a ``project_id`` column."""
    ids = scoped_project_ids(user, override_project_id)
    if ids is None:
        return query
    if ids:
        return query.filter(model.project_id.in_(ids))
    return query.filter(model.project_id.is_(None))


def ensure_visible(row, user: User) -> None:
    """Raise 404 if ``row`` is outside the caller's scope. Use this from
    detail endpoints so we don't leak the existence of other projects'
    resources (404 instead of 403)."""
    if row is None:
        return
    if is_global(user):
        return
    ids = scoped_project_ids(user)
    pid = getattr(row, "project_id", None)
    visible = (pid in ids) if ids else (pid is None)
    if not visible:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recurso no encontrado")


def cabinet_codes_in_scope(db, user: User, override_project_id: int | None = None) -> set[str] | None:
    """Return the set of cabinet codes the user can see, or ``None`` to
    signal "no restriction" (owner without override). Used by endpoints
    that key off ``cabinet_code`` rather than ``project_id`` directly."""
    from app.models.cabinet import Cabinet
    ids = scoped_project_ids(user, override_project_id)
    if ids is None:
        return None
    q = db.query(Cabinet.code)
    q = q.filter(Cabinet.project_id.in_(ids)) if ids else q.filter(Cabinet.project_id.is_(None))
    return {c.code for c in q.all()}


def filter_by_cabinet_scope(items: Iterable, codes: set[str] | None, attr: str = "cabinet_id"):
    """Filter an iterable of dicts/objects keeping only those whose
    ``cabinet_id`` (or ``attr``) is in the visible set. Pass ``codes=None``
    for the wide-open case (owner) — yields everything."""
    if codes is None:
        return list(items)
    out = []
    for it in items:
        cid = it.get(attr) if isinstance(it, dict) else getattr(it, attr, None)
        if cid in codes:
            out.append(it)
    return out
