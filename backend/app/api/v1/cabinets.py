from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.mqtt_client import bus
from app.models.cabinet import Cabinet
from app.models.user import User
from app.schemas.cabinet import CabinetCreate, CabinetRead, CabinetUpdate
from app.services import audit_log, ranks
from app.services.auth import require_permission

router = APIRouter(prefix="/cabinets", tags=["cabinets"])


def _merged(db: Session) -> list[dict]:
    """Combine live telemetry (from the bus) with registry metadata (from DB)."""
    live = {c["cabinet_id"]: c for c in bus.snapshot()}
    registry = {c.code: c for c in db.query(Cabinet).all()}
    out = []
    for code in sorted(set(live) | set(registry)):
        item = live.get(code) or {
            "cabinet_id": code,
            "online": False,
            "status": "ok",
            "telemetry": None,
            "state": {"relay": "on", "dim": 100},
            "alarms": [],
        }
        reg = registry.get(code)
        item["name"] = reg.name if reg else code
        item["zone"] = reg.zone if reg else None
        item["latitude"] = reg.latitude if reg else None
        item["longitude"] = reg.longitude if reg else None
        out.append(item)
    return out


@router.get("")
def list_cabinets(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ranks.P_CABINET_READ)),
) -> list[dict]:
    """Live snapshot of every cabinet: telemetry, state, alarms and location."""
    return _merged(db)


@router.get("/registry", response_model=list[CabinetRead])
def list_registry(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ranks.P_CABINET_READ)),
):
    return db.query(Cabinet).order_by(Cabinet.code).all()


@router.post("/registry", response_model=CabinetRead, status_code=status.HTTP_201_CREATED)
def create_cabinet(
    body: CabinetCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_MANAGE)),
) -> Cabinet:
    if db.query(Cabinet).filter(Cabinet.code == body.code).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Cabinet code already exists")
    cabinet = Cabinet(**body.model_dump())
    db.add(cabinet)
    db.commit()
    db.refresh(cabinet)
    audit_log.record(
        db, username=actor.username, action="cabinet.create", target=cabinet.code,
        detail=body.model_dump(),
    )
    return cabinet


@router.patch("/registry/{code}", response_model=CabinetRead)
def update_cabinet(
    code: str,
    body: CabinetUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_MANAGE)),
) -> Cabinet:
    cabinet = db.query(Cabinet).filter(Cabinet.code == code).first()
    if not cabinet:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cabinet not found")
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(cabinet, key, value)
    db.commit()
    db.refresh(cabinet)
    audit_log.record(
        db, username=actor.username, action="cabinet.update", target=code, detail=data
    )
    return cabinet


@router.get("/{cabinet_id}/snapshot")
def get_cabinet(
    cabinet_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ranks.P_CABINET_READ)),
) -> dict:
    for cabinet in _merged(db):
        if cabinet["cabinet_id"] == cabinet_id:
            return cabinet
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown cabinet")
