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


def test_delete_circuit_refuses_with_attached_lightpoints(client):
    owner = _owner(client)
    client.post("/api/v1/cabinets/registry",
                json={"code": "CAB-001", "name": "Centro", "number": 1}, headers=owner)
    circ = client.post("/api/v1/circuits",
                       json={"cabinet_code": "CAB-001", "number": 1}, headers=owner).json()
    client.post("/api/v1/lightpoints",
                json={"cabinet_code": "CAB-001", "circuit_id": circ["id"], "number": 1,
                      "phase": "L1"}, headers=owner)
    # Hay una luminaria → 409.
    r = client.delete(f"/api/v1/circuits/{circ['id']}", headers=owner)
    assert r.status_code == 409
    # Quitar la luminaria → ahora sí.
    point = client.get("/api/v1/lightpoints?cabinet_code=CAB-001", headers=owner).json()[0]
    client.delete(f"/api/v1/lightpoints/{point['id']}", headers=owner)
    assert client.delete(f"/api/v1/circuits/{circ['id']}", headers=owner).status_code == 200


def test_reassign_circuit_moves_lightpoints_to_new_cabinet(client):
    owner = _owner(client)
    # Dos CMs.
    client.post("/api/v1/cabinets/registry", json={"code": "CAB-A", "name": "A", "number": 1}, headers=owner)
    client.post("/api/v1/cabinets/registry", json={"code": "CAB-B", "name": "B", "number": 2}, headers=owner)
    # Circuito con 2 luminarias en CAB-A.
    circ = client.post("/api/v1/circuits", json={"cabinet_code": "CAB-A", "number": 1}, headers=owner).json()
    for n in (1, 2):
        client.post("/api/v1/lightpoints",
                    json={"cabinet_code": "CAB-A", "circuit_id": circ["id"], "number": n, "phase": "L1"},
                    headers=owner)
    # Reasignar el circuito a CAB-B.
    r = client.patch(f"/api/v1/circuits/{circ['id']}", json={"cabinet_code": "CAB-B"}, headers=owner)
    assert r.status_code == 200, r.text
    assert r.json()["cabinet_code"] == "CAB-B"
    # Las luminarias se han movido con él: CAB-A queda vacío, CAB-B con 2.
    tp = client.get("/api/v1/topology", headers=owner).json()
    a = next(c for c in tp["cabinets"] if c["code"] == "CAB-A")
    b = next(c for c in tp["cabinets"] if c["code"] == "CAB-B")
    assert len(a["points"]) == 0 and len(a["circuits"]) == 0
    assert len(b["points"]) == 2 and len(b["circuits"]) == 1


def test_reassign_circuit_to_unknown_cabinet_fails(client):
    owner = _owner(client)
    client.post("/api/v1/cabinets/registry", json={"code": "CAB-A", "name": "A", "number": 1}, headers=owner)
    circ = client.post("/api/v1/circuits", json={"cabinet_code": "CAB-A", "number": 1}, headers=owner).json()
    r = client.patch(f"/api/v1/circuits/{circ['id']}", json={"cabinet_code": "CAB-NOPE"}, headers=owner)
    assert r.status_code == 404


def test_delete_cabinet_cascades_circuits_and_points(client):
    owner = _owner(client)
    client.post("/api/v1/cabinets/registry",
                json={"code": "CAB-X", "name": "X", "number": 9}, headers=owner)
    circ = client.post("/api/v1/circuits",
                       json={"cabinet_code": "CAB-X", "number": 1}, headers=owner).json()
    client.post("/api/v1/lightpoints",
                json={"cabinet_code": "CAB-X", "circuit_id": circ["id"], "number": 1,
                      "phase": "L1"}, headers=owner)
    # Borrar el cuadro arrastra todo.
    r = client.delete("/api/v1/cabinets/registry/CAB-X", headers=owner)
    assert r.status_code == 200
    body = r.json()
    assert body["circuits"] == 1 and body["points"] == 1
    # Y ya no aparece en el árbol.
    tp = client.get("/api/v1/topology", headers=owner).json()
    assert not any(c["code"] == "CAB-X" for c in tp["cabinets"])


def test_wipe_topology_clears_everything(client):
    owner = _owner(client)
    client.post("/api/v1/cabinets/registry", json={"code": "AA", "name": "A"}, headers=owner)
    client.post("/api/v1/cabinets/registry", json={"code": "BB", "name": "B"}, headers=owner)
    r = client.post("/api/v1/cabinets/registry/wipe-all", headers=owner)
    assert r.status_code == 200, r.text
    assert r.json()["cabinets"] >= 2
    tp = client.get("/api/v1/topology", headers=owner).json()
    assert tp["cabinets"] == []
