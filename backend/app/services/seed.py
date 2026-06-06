"""Seed a demo topology (cabinets -> circuits -> light points) for the map.

Deterministic so demo data is stable across restarts. Idempotent: only fills
in what's missing.
"""
import math

from sqlalchemy.orm import Session

from app.models.cabinet import Cabinet
from app.models.circuit import Circuit
from app.models.lightpoint import LightPoint

# (code, name, zone, lat, lon, number, color) — around central Madrid.
_DEMO_CABINETS = [
    ("CAB-001", "Cuadro Centro", "Centro", 40.4168, -3.7038, 1, "#f97316"),
    ("CAB-002", "Cuadro Salamanca", "Salamanca", 40.4250, -3.6900, 2, "#a855f7"),
    ("CAB-003", "Cuadro Latina", "Latina", 40.4100, -3.7100, 3, "#22d3ee"),
    ("CAB-004", "Cuadro Chamberí", "Chamberí", 40.4300, -3.7150, 4, "#84cc16"),
]
_PHASES = ["L1", "L2", "L3"]
_CIRCUIT_COLORS = ["#38bdf8", "#f472b6"]
_POINTS_PER_CABINET = 6
_RING_RADIUS = 0.0016  # ~150 m


def seed_demo_cabinets(db: Session) -> None:
    for code, name, zone, lat, lon, number, color in _DEMO_CABINETS:
        if not db.query(Cabinet).filter(Cabinet.code == code).first():
            db.add(Cabinet(code=code, name=name, zone=zone, latitude=lat,
                           longitude=lon, number=number, color=color))
    db.commit()

    for code, name, zone, lat, lon, number, color in _DEMO_CABINETS:
        if db.query(Circuit).filter(Circuit.cabinet_code == code).count():
            continue  # already seeded for this cabinet

        circuits = []
        for ci in range(2):
            circuit = Circuit(
                cabinet_code=code, number=ci + 1, name=f"Circuito {ci + 1}",
                color=_CIRCUIT_COLORS[ci % len(_CIRCUIT_COLORS)], phase="III",
            )
            db.add(circuit)
            db.flush()  # assign id
            circuits.append(circuit)

        for k in range(_POINTS_PER_CABINET):
            angle = (k / _POINTS_PER_CABINET) * 2 * math.pi
            plat = lat + _RING_RADIUS * math.cos(angle)
            plon = lon + _RING_RADIUS * math.sin(angle) / math.cos(math.radians(lat))
            circuit = circuits[k % len(circuits)]
            db.add(LightPoint(
                cabinet_code=code, circuit_id=circuit.id, number=k + 1,
                label=f"Farola {number}.{k + 1}", phase=_PHASES[k % 3],
                latitude=plat, longitude=plon, power_w=100 + k * 5,
            ))
    db.commit()
