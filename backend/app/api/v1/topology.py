import csv
import io

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
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
    LightCatalog,
    LightPointCreate,
    LightPointRead,
    LightPointUpdate,
)


# Valores por defecto que la UI puede sugerir aunque la BD esté vacía.
# La unión con lo ya usado en BD se hace en el endpoint /lightpoints/catalog.
_DEFAULT_TECHNOLOGIES = ["LED", "Vapor sodio alta presión", "Halogenuros metálicos",
                          "Fluorescente", "Mercurio (legado)", "Otro"]
_DEFAULT_REGULATIONS = ["Ninguna", "1-10 V", "DALI", "Autónoma (driver)", "PLC", "Otro"]
_DEFAULT_COLOR_TEMPS = ["2200K", "2700K", "3000K", "4000K", "5700K", "6500K"]
_DEFAULT_SUPPORT_TYPES = ["Columna", "Brazo mural", "Báculo", "Catenaria", "Pescante", "Otro"]
_DEFAULT_LAYOUT_TYPES = ["Unilateral", "Bilateral pareada", "Bilateral tresbolillo",
                          "Central (mediana)", "Suspensión cable", "Otro"]
_DEFAULT_LIGHT_SOURCE_TYPES = ["LED", "VSAP", "VSBP", "HM", "Mercurio", "Halógena", "Otro"]
from app.services import audit_log, ranks, tenancy
from app.services.auth import require_permission

router = APIRouter(tags=["topology"])

# Fixed phase colours (clear on a dark map; tweak to taste / IEC if needed).
PHASE_COLORS = {"L1": "#ef4444", "L2": "#f59e0b", "L3": "#38bdf8"}


def _recompute_circuit_power(db: Session, circuit_id: int | None) -> None:
    """Recalcula la potencia nominal del circuito = suma de las luminarias que
    cuelgan de él. Mantiene Circuit.expected_power_w al día (motor de alarmas y
    listados) para que nadie tenga que teclear el nominal a mano. Sin luminarias
    → 0 → sin comprobación de carga."""
    if not circuit_id:
        return
    circuit = db.get(Circuit, circuit_id)
    if not circuit:
        return
    total = sum(
        (p.power_w or 0.0)
        for p in db.query(LightPoint).filter(LightPoint.circuit_id == circuit_id).all()
    )
    circuit.expected_power_w = float(total)


def _ensure_cabinet_visible(db: Session, actor: User, cabinet_code: str) -> None:
    """El proyecto manda dónde: comprueba que el cuadro existe y está en el
    scope del actor. Un no-owner sobre un código fuera de su ciudad → 404."""
    cab = db.query(Cabinet).filter(Cabinet.code == cabinet_code).first()
    if cab is None:
        if not tenancy.is_global(actor):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Cuadro no encontrado")
        return
    tenancy.ensure_visible(cab, actor)


@router.get("/topology")
def get_topology(
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_READ)),
) -> dict:
    """Full tree for the map: cabinets (CM) -> circuits -> light points, with
    live status merged in and the phase colour key. Multi-tenant: solo los
    cuadros del scope del usuario (el owner los ve todos)."""
    codes = tenancy.cabinet_codes_in_scope(db, actor, None)
    live = {c["cabinet_id"]: c for c in bus.snapshot()}
    circuits = db.query(Circuit).all()
    points = db.query(LightPoint).all()

    # Nominal por circuito = suma automática de las luminarias que cuelgan de él.
    power_by_circuit: dict[int, float] = {}
    for p in points:
        if p.circuit_id is not None:
            power_by_circuit[p.circuit_id] = (
                power_by_circuit.get(p.circuit_id, 0.0) + (p.power_w or 0.0)
            )

    cabinets = []
    for cab in db.query(Cabinet).order_by(Cabinet.number, Cabinet.code).all():
        if codes is not None and cab.code not in codes:
            continue  # fuera del scope del usuario
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
                     "expected_power_w": power_by_circuit.get(c.id, 0.0)}
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
                        # Ficha extendida estilo RF Light GEO (todos opcionales).
                        "inventory_code": p.inventory_code or "",
                        "technology": p.technology or "",
                        "manufacturer": p.manufacturer or "",
                        "model": p.model or "",
                        "photometric": p.photometric or "",
                        "regulation": p.regulation or "",
                        "serial_number": p.serial_number or "",
                        "color_temp_k": p.color_temp_k or "",
                        "network_id": p.network_id or "",
                        "province": p.province or "",
                        "locality": p.locality or "",
                        "postal_code": p.postal_code or "",
                        "street": p.street or "",
                        "street_number": p.street_number or "",
                        "notes": p.notes or "",
                        "support_type": p.support_type or "",
                        "layout_type": p.layout_type or "",
                        "construction_type": p.construction_type or "",
                        "light_source_type": p.light_source_type or "",
                        "old_manufacturer": p.old_manufacturer or "",
                        "old_model": p.old_model or "",
                        "old_power_w": p.old_power_w or 0.0,
                        "old_light_source_type": p.old_light_source_type or "",
                        "old_notes": p.old_notes or "",
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
    actor: User = Depends(require_permission(ranks.P_CABINET_READ)),
):
    query = db.query(Circuit)
    if cabinet_code:
        query = query.filter(Circuit.cabinet_code == cabinet_code)
    codes = tenancy.cabinet_codes_in_scope(db, actor, None)
    if codes is not None:
        query = query.filter(Circuit.cabinet_code.in_(codes))
    return query.order_by(Circuit.cabinet_code, Circuit.number).all()


@router.post("/circuits", response_model=CircuitRead, status_code=status.HTTP_201_CREATED)
def create_circuit(
    body: CircuitCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_MANAGE)),
) -> Circuit:
    _ensure_cabinet_visible(db, actor, body.cabinet_code)
    circuit = Circuit(**body.model_dump())
    db.add(circuit)
    db.commit()
    db.refresh(circuit)
    # El nominal se calcula solo (suma de luminarias); un circuito nuevo aún no
    # tiene ninguna → 0.
    _recompute_circuit_power(db, circuit.id)
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
    _ensure_cabinet_visible(db, actor, circuit.cabinet_code)  # no editar fuera de tu scope
    data = body.model_dump(exclude_unset=True)

    # Reasignación a otro CM: validar destino y arrastrar las luminarias del
    # circuito (su cabinet_code) para que no queden huérfanas en el viejo CM.
    moved_lights = 0
    new_code = data.pop("cabinet_code", None)
    if new_code and new_code != circuit.cabinet_code:
        _ensure_cabinet_visible(db, actor, new_code)  # destino también en tu scope
        if not db.query(Cabinet).filter(Cabinet.code == new_code).first():
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"CM destino no encontrado: {new_code}")
        old_code = circuit.cabinet_code
        circuit.cabinet_code = new_code
        for lp in db.query(LightPoint).filter(LightPoint.circuit_id == circuit.id):
            lp.cabinet_code = new_code
            moved_lights += 1
        audit_log.record(
            db, username=actor.username, action="circuit.reassign",
            target=str(circuit_id), detail={"from": old_code, "to": new_code, "lights": moved_lights},
        )

    # El nominal es automático: ignoramos cualquier valor manual que llegue en
    # el body y lo recalculamos desde las luminarias del circuito.
    data.pop("expected_power_w", None)
    for key, value in data.items():
        setattr(circuit, key, value)
    db.commit()
    _recompute_circuit_power(db, circuit.id)
    db.commit()
    db.refresh(circuit)
    if not new_code:
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
    _ensure_cabinet_visible(db, actor, circuit.cabinet_code)
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
@router.get("/lightpoints/catalog", response_model=LightCatalog)
def light_catalog(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ranks.P_CABINET_READ)),
) -> LightCatalog:
    """Datos para los selectores con autocompletado del formulario de
    luminaria. Cada lista es la unión de los valores ya usados en BD +
    los defaults razonables, ordenada y sin duplicados (case-insensitive).

    Así, en cuanto el técnico registra un fabricante una vez, sale en el
    autocompletado para las siguientes luminarias — justo lo que el capitán
    pedía: ya registrados, solo buscarlos.
    """
    def merge(field, defaults):
        used = {(v or "").strip() for v in db.query(field).distinct().all() for v in v}
        return sorted({*defaults, *(v for v in used if v)}, key=str.casefold)

    # SQLAlchemy distinct() devuelve tuplas: simplifico.
    def uniq(col):
        rows = db.query(col).distinct().all()
        out = set()
        for (v,) in rows:
            if v:
                out.add(str(v).strip())
        return out

    return LightCatalog(
        technologies=sorted({*_DEFAULT_TECHNOLOGIES, *uniq(LightPoint.technology)}, key=str.casefold),
        manufacturers=sorted(uniq(LightPoint.manufacturer), key=str.casefold),
        models=sorted(uniq(LightPoint.model), key=str.casefold),
        regulations=sorted({*_DEFAULT_REGULATIONS, *uniq(LightPoint.regulation)}, key=str.casefold),
        color_temps=sorted({*_DEFAULT_COLOR_TEMPS, *uniq(LightPoint.color_temp_k)}, key=str.casefold),
        support_types=sorted({*_DEFAULT_SUPPORT_TYPES, *uniq(LightPoint.support_type)}, key=str.casefold),
        layout_types=sorted({*_DEFAULT_LAYOUT_TYPES, *uniq(LightPoint.layout_type)}, key=str.casefold),
        light_source_types=sorted({*_DEFAULT_LIGHT_SOURCE_TYPES, *uniq(LightPoint.light_source_type)}, key=str.casefold),
    )


@router.get("/lightpoints", response_model=list[LightPointRead])
def list_lightpoints(
    cabinet_code: str | None = None,
    circuit_id: int | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_READ)),
):
    query = db.query(LightPoint)
    if cabinet_code:
        query = query.filter(LightPoint.cabinet_code == cabinet_code)
    if circuit_id:
        query = query.filter(LightPoint.circuit_id == circuit_id)
    codes = tenancy.cabinet_codes_in_scope(db, actor, None)
    if codes is not None:
        query = query.filter(LightPoint.cabinet_code.in_(codes))
    return query.order_by(LightPoint.cabinet_code, LightPoint.number).all()


@router.post("/lightpoints", response_model=LightPointRead, status_code=status.HTTP_201_CREATED)
def create_lightpoint(
    body: LightPointCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_MANAGE)),
) -> LightPoint:
    _ensure_cabinet_visible(db, actor, body.cabinet_code)
    point = LightPoint(**body.model_dump())
    db.add(point)
    db.commit()
    db.refresh(point)
    _recompute_circuit_power(db, point.circuit_id)
    db.commit()
    audit_log.record(
        db, username=actor.username, action="lightpoint.create",
        target=f"{body.cabinet_code}/F{body.number}", detail=body.model_dump(),
    )
    return point


class CsvImport(BaseModel):
    csv: str


def _g(row: dict, *keys: str) -> str:
    """Primer valor no vacío entre varias cabeceras posibles (tolera acentos)."""
    for k in keys:
        v = (row.get(k) or "").strip()
        if v:
            return v
    return ""


@router.post("/lightpoints/import")
def import_lightpoints(
    body: CsvImport,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_MANAGE)),
) -> dict:
    """Carga masiva de luminarias desde un CSV (mismo formato que el export):
    Nº, Calle, Nº calle, Localidad, Provincia, CP, CM, Circuito, Fase,
    Fabricante, Modelo, W, Inventario, Tecnología.

    UPSERT por (CM, Nº): si la luminaria existe la actualiza, si no la crea. El
    circuito se resuelve por (CM, Nº de circuito); si no existe, se crea.
    Multi-tenant: las filas de cuadros fuera del scope se ignoran con aviso.
    Robusto: una fila mala no aborta el resto; se devuelve el resumen."""
    text = (body.csv or "").lstrip("﻿")
    if not text.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "CSV vacío")
    reader = csv.DictReader(io.StringIO(text))
    created = updated = 0
    errors: list[str] = []
    affected: set[int] = set()
    visible = tenancy.cabinet_codes_in_scope(db, actor, None)
    for i, row in enumerate(reader, start=2):  # fila 1 = cabeceras
        try:
            cm = _g(row, "CM")
            num_s = _g(row, "Nº", "Nº ", "N")
            if not cm or not num_s:
                errors.append(f"fila {i}: faltan CM o Nº")
                continue
            num = int(float(num_s))
            if visible is not None and cm not in visible:
                errors.append(f"fila {i}: CM {cm} fuera de tu ámbito")
                continue
            cab = db.query(Cabinet).filter(Cabinet.code == cm).first()
            if cab is None:
                errors.append(f"fila {i}: CM {cm} no existe")
                continue
            cnum = int(float(_g(row, "Circuito") or 1))
            circ = db.query(Circuit).filter(
                Circuit.cabinet_code == cm, Circuit.number == cnum
            ).first()
            if circ is None:
                circ = Circuit(cabinet_code=cm, number=cnum, name="")
                db.add(circ)
                db.flush()
            try:
                power = float(_g(row, "W") or 0)
            except ValueError:
                power = 0.0
            fields = {
                "circuit_id": circ.id,
                "phase": _g(row, "Fase") or "L1",
                "street": _g(row, "Calle"),
                "street_number": _g(row, "Nº calle"),
                "locality": _g(row, "Localidad"),
                "province": _g(row, "Provincia"),
                "postal_code": _g(row, "CP"),
                "manufacturer": _g(row, "Fabricante"),
                "model": _g(row, "Modelo"),
                "power_w": power,
                "inventory_code": _g(row, "Inventario"),
                "technology": _g(row, "Tecnología", "Tecnologia"),
            }
            lp = db.query(LightPoint).filter(
                LightPoint.cabinet_code == cm, LightPoint.number == num
            ).first()
            if lp:
                for k, v in fields.items():
                    setattr(lp, k, v)
                updated += 1
            else:
                db.add(LightPoint(cabinet_code=cm, number=num, **fields))
                created += 1
            affected.add(circ.id)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"fila {i}: {exc}")
    db.commit()
    for cid in affected:
        _recompute_circuit_power(db, cid)
    db.commit()
    audit_log.record(
        db, username=actor.username, action="lightpoint.import",
        detail={"created": created, "updated": updated, "errors": len(errors)},
    )
    return {"created": created, "updated": updated, "errors": errors}


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
    _ensure_cabinet_visible(db, actor, point.cabinet_code)
    old_circuit_id = point.circuit_id
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(point, key, value)
    db.commit()
    db.refresh(point)
    # Si cambió la potencia o el circuito, recalculo el nominal de ambos
    # circuitos afectados (origen y destino).
    _recompute_circuit_power(db, point.circuit_id)
    if old_circuit_id != point.circuit_id:
        _recompute_circuit_power(db, old_circuit_id)
    db.commit()
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
    _ensure_cabinet_visible(db, actor, point.cabinet_code)
    circuit_id = point.circuit_id
    db.delete(point)
    db.commit()
    _recompute_circuit_power(db, circuit_id)
    db.commit()
    audit_log.record(db, username=actor.username, action="lightpoint.delete", target=str(point_id))
    return {"deleted": True}
