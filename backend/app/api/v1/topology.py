from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.mqtt_client import bus
from app.models.cabinet import Cabinet
from app.models.circuit import Circuit
from app.models.lightpoint import LightPoint
from app.models.user import User
from app.schemas.topology import (
    CircuitCreate,
    CircuitRead,
    CircuitUpdate,
    LightPointCreate,
    LightPointRead,
    LightPointUpdate,
)
from app.services import audit_log, ranks
from app.services.auth import require_permission

router = APIRouter(tags=["topology"])

# Fixed phase colours (clear on a dark map; tweak to taste / IEC if needed).
PHASE_COLORS = {"L1": "#ef4444", "L2": "#f59e0b", "L3": "#38bdf8"}


@router.get("/topology")
def get_topology(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ranks.P_CABINET_READ)),
) -> dict:
    """Full tree for the map: cabinets (CM) -> circuits -> light points, with
    live status merged in and the phase colour key."""
    live = {c["cabinet_id"]: c for c in bus.snapshot()}
    circuits = db.query(Circuit).all()
    points = db.query(LightPoint).all()

    cabinets = []
    for cab in db.query(Cabinet).order_by(Cabinet.number, Cabinet.code).all():
        snap = live.get(cab.code, {})
        cabinets.append(
            {
                "code": cab.code,
                "name": cab.name,
                "number": cab.number,
                "color": cab.color,
                "zone": cab.zone,
                "latitude": cab.latitude,
                "longitude": cab.longitude,
                "online": snap.get("online", False),
                "status": snap.get("status", "ok"),
                "telemetry": snap.get("telemetry"),
                "circuits": [
                    {"id": c.id, "number": c.number, "name": c.name,
                     "color": c.color, "phase": c.phase,
                     "expected_power_w": c.expected_power_w or 0.0}
                    for c in circuits
                    if c.cabinet_code == cab.code
                ],
                "points": [
                    {
                        "id": p.id,
                        "circuit_id": p.circuit_id,
                        "number": p.number,
                        "label": p.label,
                        "phase": p.phase,
                        "latitude": p.latitude,
                        "longitude": p.longitude,
                        "power_w": p.power_w,
                    }
                    for p in points
                    if p.cabinet_code == cab.code
                ],
            }
        )
    return {"cabinets": cabinets, "phase_colors": PHASE_COLORS}


# --------------------------- Circuits ---------------------------
@router.get("/circuits", response_model=list[CircuitRead])
def list_circuits(
    cabinet_code: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ranks.P_CABINET_READ)),
):
    query = db.query(Circuit)
    if cabinet_code:
        query = query.filter(Circuit.cabinet_code == cabinet_code)
    return query.order_by(Circuit.cabinet_code, Circuit.number).all()


@router.post("/circuits", response_model=CircuitRead, status_code=status.HTTP_201_CREATED)
def create_circuit(
    body: CircuitCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_MANAGE)),
) -> Circuit:
    circuit = Circuit(**body.model_dump())
    db.add(circuit)
    db.commit()
    db.refresh(circuit)
    audit_log.record(
        db, username=actor.username, action="circuit.create",
        target=f"{body.cabinet_code}/C{body.number}", detail=body.model_dump(),
    )
    return circuit


@router.patch("/circuits/{circuit_id}", response_model=CircuitRead)
def update_circuit(
    circuit_id: int,
    body: CircuitUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_MANAGE)),
) -> Circuit:
    circuit = db.get(Circuit, circuit_id)
    if not circuit:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Circuit not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(circuit, key, value)
    db.commit()
    db.refresh(circuit)
    audit_log.record(db, username=actor.username, action="circuit.update", target=str(circuit_id))
    return circuit


@router.delete("/circuits/{circuit_id}")
def delete_circuit(
    circuit_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_MANAGE)),
) -> dict:
    """Delete a circuit. Refuses while it still has light points attached
    — the admin must rehome or delete the lamps first to avoid orphan rows."""
    circuit = db.get(Circuit, circuit_id)
    if not circuit:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Circuit not found")
    attached = db.query(LightPoint).filter(LightPoint.circuit_id == circuit_id).count()
    if attached:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"No se puede borrar: {attached} luminaria(s) aún cuelgan de este circuito.",
        )
    code = circuit.cabinet_code
    db.delete(circuit)
    db.commit()
    audit_log.record(
        db, username=actor.username, action="circuit.delete",
        target=f"{code}/{circuit_id}",
    )
    return {"deleted": True}


# --------------------------- Light points ---------------------------
@router.get("/lightpoints", response_model=list[LightPointRead])
def list_lightpoints(
    cabinet_code: str | None = None,
    circuit_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ranks.P_CABINET_READ)),
):
    query = db.query(LightPoint)
    if cabinet_code:
        query = query.filter(LightPoint.cabinet_code == cabinet_code)
    if circuit_id:
        query = query.filter(LightPoint.circuit_id == circuit_id)
    return query.order_by(LightPoint.cabinet_code, LightPoint.number).all()


@router.post("/lightpoints", response_model=LightPointRead, status_code=status.HTTP_201_CREATED)
def create_lightpoint(
    body: LightPointCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_MANAGE)),
) -> LightPoint:
    point = LightPoint(**body.model_dump())
    db.add(point)
    db.commit()
    db.refresh(point)
    audit_log.record(
        db, username=actor.username, action="lightpoint.create",
        target=f"{body.cabinet_code}/F{body.number}", detail=body.model_dump(),
    )
    return point


@router.patch("/lightpoints/{point_id}", response_model=LightPointRead)
def update_lightpoint(
    point_id: int,
    body: LightPointUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_MANAGE)),
) -> LightPoint:
    point = db.get(LightPoint, point_id)
    if not point:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Light point not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(point, key, value)
    db.commit()
    db.refresh(point)
    audit_log.record(db, username=actor.username, action="lightpoint.update", target=str(point_id))
    return point


@router.delete("/lightpoints/{point_id}")
def delete_lightpoint(
    point_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_MANAGE)),
) -> dict:
    point = db.get(LightPoint, point_id)
    if not point:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Light point not found")
    db.delete(point)
    db.commit()
    audit_log.record(db, username=actor.username, action="lightpoint.delete", target=str(point_id))
    return {"deleted": True}
