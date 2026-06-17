"""Admin endpoints for the active-defence panel: banlist, whitelist, siege
mode and per-user device list. All gated on ``user:manage`` so only project
admins / owners can touch them.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.schemas.security import (
    DeviceRead,
    IpBanCreate,
    IpBanRead,
    SiegeToggle,
    WhitelistAdd,
)
from app.services import device_guard, ip_guard, ranks
from app.services.auth import get_current_user, require_permission

router = APIRouter(prefix="/security", tags=["security"])


# --- IP bans ----------------------------------------------------------------
@router.get("/bans", response_model=list[IpBanRead])
def list_bans(
    include_expired: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ranks.P_USER_MANAGE)),
):
    return ip_guard.list_bans(db, include_expired=include_expired)


@router.post("/bans", response_model=IpBanRead, status_code=status.HTTP_201_CREATED)
def create_ban(
    body: IpBanCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
):
    return ip_guard.ban(db, body.ip, reason=body.reason, banned_by=actor.username,
                        minutes=body.minutes)


@router.delete("/bans/{ip}")
def remove_ban(
    ip: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
):
    removed = ip_guard.unban(db, ip, by=actor.username)
    return {"removed": removed}


# --- Siege mode + whitelist -------------------------------------------------
@router.get("/siege")
def get_siege(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ranks.P_USER_MANAGE)),
):
    return {"on": ip_guard.siege_active(db), "whitelist": ip_guard.list_whitelist(db)}


@router.post("/siege")
def toggle_siege(
    body: SiegeToggle,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
):
    # Siege is owner-only — it can lock the project admin themselves out.
    if actor.rank != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el owner puede activar el modo siege")
    changed = ip_guard.set_siege(db, on=body.on, by=actor.username)
    return {"on": ip_guard.siege_active(db), "changed": changed}


@router.post("/whitelist")
def whitelist_add(
    body: WhitelistAdd,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
):
    ip_guard.whitelist_add(db, body.ip, by=actor.username)
    return {"whitelist": ip_guard.list_whitelist(db)}


@router.delete("/whitelist/{ip}")
def whitelist_remove(
    ip: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
):
    ip_guard.whitelist_remove(db, ip, by=actor.username)
    return {"whitelist": ip_guard.list_whitelist(db)}


# --- User devices -----------------------------------------------------------
@router.get("/devices", response_model=list[DeviceRead])
def my_devices(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """The current user's own device list — every user can manage their own."""
    return device_guard.list_devices(db, user.id)


@router.delete("/devices/{device_id}")
def revoke_my_device(
    device_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not device_guard.revoke_device(db, user_id=user.id,
                                      username=user.username, device_id=device_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispositivo no encontrado")
    return {"ok": True}
