"""Seed a demo topology (cabinets -> circuits -> light points) for the map.

Deterministic so demo data is stable across restarts. Idempotent: only fills
in what's missing.
"""
import math

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.cabinet import Cabinet
from app.models.circuit import Circuit
from app.models.lightpoint import LightPoint
from app.models.project import Project
from app.models.user import User


DEMO_PIN = "1234"
DEMO_PATTERN = "01258"  # diagonal Z — easy to remember in the demo


def seed_demo_admin(db: Session, username: str, password: str) -> None:
    """Create a known owner account with PIN + pattern so the demo can log in
    through the full 4-credential flow out of the box (idempotent). The account
    ships with a fully filled-in worker profile so the ficha has something to
    show in the demo."""
    if db.query(User).filter(User.username == username).first():
        return
    db.add(User(
        username=username,
        password_hash=hash_password(password),
        pin_hash=hash_password(DEMO_PIN),
        pattern_hash=hash_password(DEMO_PATTERN),
        rank="owner",
        # Ficha demo — pack laboral
        full_name="Phoenix Owner (demo)",
        phone="+34 600 000 000",
        job_title="Responsable de plataforma",
        department="Operaciones",
        site="Madrid Centro",
        shift="oficina",
        # Pack contractual — interno: solo nº empleado, sin DNI ni empresa
        employee_id="PHX-0001",
        notes="Cuenta de demostración sembrada al arrancar.",
    ))
    db.commit()

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
    # Ensure a demo project exists so the multi-tenant filter has something
    # to chew on out of the box. Idempotent.
    project = db.query(Project).filter(Project.code == "madrid").first()
    if project is None:
        project = Project(code="madrid", name="Madrid Centro")
        db.add(project)
        db.commit()
        db.refresh(project)

    for code, name, zone, lat, lon, number, color in _DEMO_CABINETS:
        existing = db.query(Cabinet).filter(Cabinet.code == code).first()
        if existing is None:
            db.add(Cabinet(code=code, name=name, zone=zone, latitude=lat,
                           longitude=lon, number=number, color=color,
                           project_id=project.id))
        elif existing.project_id is None:
            existing.project_id = project.id
    db.commit()

    for code, name, zone, lat, lon, number, color in _DEMO_CABINETS:
        if db.query(Circuit).filter(Circuit.cabinet_code == code).count():
            continue  # already seeded for this cabinet

        circuits = []
        for ci in range(2):
            circuit = Circuit(
                cabinet_code=code, number=ci + 1, name="",
                color=_CIRCUIT_COLORS[ci % len(_CIRCUIT_COLORS)],
                phase=_PHASES[ci % len(_PHASES)],
                # Half the points hang off each circuit; nominal is the sum
                # of their power. Demo loop simulates departures from this.
                expected_power_w=sum(
                    100 + k * 5
                    for k in range(_POINTS_PER_CABINET)
                    if k % 2 == ci
                ),
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
                label=f"Farola {k + 1:02d}", phase=_PHASES[k % 3],
                latitude=plat, longitude=plon, power_w=100 + k * 5,
            ))
    db.commit()
