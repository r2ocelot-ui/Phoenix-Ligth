"""CRUD for the device registry (SICE-style cabinet ↔ controller binding)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.cabinet import Cabinet
from app.models.device import Device
from app.models.user import User
from app.schemas.device import DeviceCreate, DeviceRead
from app.services import audit_log, ranks
from app.services.auth import require_permission

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceRead])
def list_devices(
    cabinet_code: str | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ranks.P_CABINET_READ)),
):
    q = db.query(Device).order_by(Device.id.desc())
    if cabinet_code:
        q = q.filter(Device.cabinet_code == cabinet_code)
    if not include_inactive:
        q = q.filter(Device.is_active.is_(True))
    return q.all()


@router.post("", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
def register_device(
    body: DeviceCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_MANAGE)),
):
    if not db.query(Cabinet).filter(Cabinet.code == body.cabinet_code).first():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cuadro no encontrado")
    if db.query(Device).filter(Device.serial == body.serial).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese serial ya está registrado")
    # Replace any other active binding for this cabinet — only one at a time.
    for stale in db.query(Device).filter(
        Device.cabinet_code == body.cabinet_code, Device.is_active.is_(True)
    ):
        stale.is_active = False
        db.add(stale)

    device = Device(
        cabinet_code=body.cabinet_code, serial=body.serial,
        imei=body.imei, model=body.model, firmware=body.firmware,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    audit_log.record(
        db, username=actor.username, action="device.register",
        target=body.cabinet_code,
        detail={"serial": body.serial, "imei": body.imei, "model": body.model},
    )
    return device


@router.delete("/{device_id}")
def deactivate_device(
    device_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_MANAGE)),
):
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispositivo no encontrado")
    if not device.is_active:
        return {"ok": True, "already": True}
    device.is_active = False
    db.commit()
    audit_log.record(
        db, username=actor.username, action="device.deactivate",
        target=device.cabinet_code, detail={"serial": device.serial},
    )
    return {"ok": True}
