from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.schemas.user import (
    PermissionOverride,
    RankChange,
    UserDetail,
    UserRead,
)
from app.services import audit_log, ranks
from app.services.auth import require_permission, user_detail

router = APIRouter(prefix="/users", tags=["users"])


def _get(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


@router.get("", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ranks.P_USER_VIEW)),
):
    return db.query(User).order_by(User.id).all()


@router.get("/{user_id}", response_model=UserDetail)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ranks.P_USER_VIEW)),
) -> UserDetail:
    return user_detail(_get(db, user_id))


@router.post("/{user_id}/rank", response_model=UserRead)
def change_rank(
    user_id: int,
    body: RankChange,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
) -> User:
    if body.rank not in ranks.RANKS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown rank: {body.rank}")
    if ranks.rank_level(body.rank) > ranks.rank_level(actor.rank):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot assign a rank above your own")

    user = _get(db, user_id)
    old = user.rank
    user.rank = body.rank
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
    user = _get(db, user_id)
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

    user = _get(db, user_id)
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
    return user_detail(user)
