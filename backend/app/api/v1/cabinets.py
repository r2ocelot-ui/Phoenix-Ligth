from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.mqtt_client import bus
from app.models.cabinet import Cabinet
from app.models.user import User
from app.schemas.cabinet import CabinetCreate, CabinetRead, CabinetUpdate
from app.services import audit_log, ranks, tenancy
from app.services.auth import get_current_user, require_permission

router = APIRouter(prefix="/cabinets", tags=["cabinets"])


def _merged(db: Session, visible_codes: set[str] | None) -> list[dict]:
    """Combine live telemetry (from the bus) with registry metadata (from DB).
    ``visible_codes`` filters the result to the caller's project scope; pass
    ``None`` to skip the filter (owner without an active project filter)."""
    live = {c["cabinet_id"]: c for c in bus.snapshot()}
    registry = {c.code: c for c in db.query(Cabinet).all()}
    out = []
    for code in sorted(set(live) | set(registry)):
        if visible_codes is not None and code not in visible_codes:
            continue
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
        item["number"] = reg.number if reg else 0
        item["color"] = reg.color if reg else "#f97316"
        item["zone"] = reg.zone if reg else None
        item["latitude"] = reg.latitude if reg else None
        item["longitude"] = reg.longitude if reg else None
        item["project_id"] = reg.project_id if reg else None
        out.append(item)
    return out


@router.get("")
def list_cabinets(
    project_id: int | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_READ)),
) -> list[dict]:
    """Live snapshot of every cabinet: telemetry, state, alarms and location."""
    codes = tenancy.cabinet_codes_in_scope(db, actor, project_id)
    return _merged(db, codes)


@router.get("/registry", response_model=list[CabinetRead])
def list_registry(
    project_id: int | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_READ)),
):
    q = db.query(Cabinet).order_by(Cabinet.code)
    q = tenancy.scope_query(q, Cabinet, actor, project_id)
    return q.all()


@router.post("/registry", response_model=CabinetRead, status_code=status.HTTP_201_CREATED)
def create_cabinet(
    body: CabinetCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_MANAGE)),
) -> Cabinet:
    if db.query(Cabinet).filter(Cabinet.code == body.code).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Cabinet code already exists")
    payload = body.model_dump()
    # A non-owner pins the new cabinet to their own project. Owner stays
    # global by default (can move it to a project from the Projects panel).
    if not tenancy.is_global(actor):
        payload["project_id"] = actor.project_id
    cabinet = Cabinet(**payload)
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
