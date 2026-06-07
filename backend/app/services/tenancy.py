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


def effective_scope(user: User, override_project_id: int | None) -> int | None | object:
    """Return the project id to filter by, or the sentinel ``NO_FILTER`` when
    the caller may see everything.

    - For owners, the override (if any) wins. Without override, no filter.
    - For non-owners the override is ignored: their assignment is the law.
    """
    if is_global(user):
        if override_project_id is not None:
            return override_project_id
        return NO_FILTER
    return user.project_id


NO_FILTER = object()  # sentinel for "no scoping needed"


def scope_query(query: Query, model, user: User, override_project_id: int | None = None) -> Query:
    """Apply the project filter to a SQLAlchemy query against ``model``.
    ``model`` must expose a ``project_id`` column."""
    scope = effective_scope(user, override_project_id)
    if scope is NO_FILTER:
        return query
    return query.filter(model.project_id == scope)


def ensure_visible(row, user: User) -> None:
    """Raise 404 if ``row`` is outside the caller's scope. Use this from
    detail endpoints so we don't leak the existence of other projects'
    resources (404 instead of 403)."""
    if row is None:
        return
    if is_global(user):
        return
    if getattr(row, "project_id", None) != user.project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recurso no encontrado")


def cabinet_codes_in_scope(db, user: User, override_project_id: int | None = None) -> set[str] | None:
    """Return the set of cabinet codes the user can see, or ``None`` to
    signal "no restriction" (owner without override). Used by endpoints
    that key off ``cabinet_code`` rather than ``project_id`` directly."""
    from app.models.cabinet import Cabinet
    scope = effective_scope(user, override_project_id)
    if scope is NO_FILTER:
        return None
    return {c.code for c in db.query(Cabinet.code).filter(Cabinet.project_id == scope).all()}


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
