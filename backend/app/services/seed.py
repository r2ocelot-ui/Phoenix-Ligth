"""Seed demo cabinets so the map has something to show in demo mode."""
from sqlalchemy.orm import Session

from app.models.cabinet import Cabinet

# (code, name, zone, lat, lon) — placed around central Madrid.
_DEMO_CABINETS = [
    ("CAB-001", "Cuadro Centro", "Centro", 40.4168, -3.7038),
    ("CAB-002", "Cuadro Salamanca", "Salamanca", 40.4250, -3.6900),
    ("CAB-003", "Cuadro Latina", "Latina", 40.4100, -3.7100),
    ("CAB-004", "Cuadro Chamberí", "Chamberí", 40.4300, -3.7150),
]


def seed_demo_cabinets(db: Session) -> None:
    for code, name, zone, lat, lon in _DEMO_CABINETS:
        if not db.query(Cabinet).filter(Cabinet.code == code).first():
            db.add(Cabinet(code=code, name=name, zone=zone, latitude=lat, longitude=lon))
    db.commit()
