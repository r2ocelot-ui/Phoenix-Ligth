import pytest
from app.core.database import Base, get_db
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    from app.models import audit, cabinet, circuit, device, lightpoint, role, security, user  # noqa: F401

    Base.metadata.create_all(engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _owner(client):
    client.post("/api/v1/auth/register", json={"username": "boss", "password": "secret123"})
    tok = client.post("/api/v1/auth/login", data={"username": "boss", "password": "secret123"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _novato(client):
    # 'boss' (owner) must already exist; create a novato via the admin endpoint.
    owner = client.post("/api/v1/auth/login", data={"username": "boss", "password": "secret123"}).json()["access_token"]
    client.post(
        "/api/v1/users",
        json={"username": "newbie", "password": "secret123", "rank": "novato"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    tok = client.post("/api/v1/auth/login", data={"username": "newbie", "password": "secret123"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_topology_requires_auth(client):
    assert client.get("/api/v1/topology").status_code == 401


def test_topology_tree_with_phase_colors(client):
    owner = _owner(client)
    # CM
    client.post("/api/v1/cabinets/registry",
                json={"code": "CAB-001", "name": "Centro", "number": 1, "latitude": 40.4, "longitude": -3.7},
                headers=owner)
    # circuit
    circ = client.post("/api/v1/circuits",
                       json={"cabinet_code": "CAB-001", "number": 1, "color": "#38bdf8"},
                       headers=owner).json()
    # light point on L2
    client.post("/api/v1/lightpoints",
                json={"cabinet_code": "CAB-001", "circuit_id": circ["id"], "number": 1,
                      "phase": "L2", "latitude": 40.401, "longitude": -3.701, "power_w": 120},
                headers=owner)

    tp = client.get("/api/v1/topology", headers=owner).json()
    assert tp["phase_colors"]["L2"] == "#f59e0b"
    cab = next(c for c in tp["cabinets"] if c["code"] == "CAB-001")
    assert cab["number"] == 1
    assert len(cab["circuits"]) == 1
    assert len(cab["points"]) == 1
    assert cab["points"][0]["phase"] == "L2"


def test_topology_mutations_require_manage(client):
    _owner(client)            # first user becomes owner
    novato = _novato(client)  # second user is a novato
    r = client.post("/api/v1/circuits", json={"cabinet_code": "CAB-001", "number": 1}, headers=novato)
    assert r.status_code == 403
    r = client.post("/api/v1/lightpoints",
                    json={"cabinet_code": "CAB-001", "circuit_id": 1, "number": 1}, headers=novato)
    assert r.status_code == 403
