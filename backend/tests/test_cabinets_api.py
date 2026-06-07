import app.core.mqtt_client as mqtt_module
import pytest
from app.core.database import Base, get_db
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    from app.models import audit, user  # noqa: F401

    Base.metadata.create_all(engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # Reset bus snapshot between tests.
    mqtt_module.bus.active_alarms.clear()
    mqtt_module.bus.last_telemetry.clear()
    mqtt_module.bus.cabinet_state.clear()
    mqtt_module.bus._known_cabinets.clear()
    yield TestClient(app)
    app.dependency_overrides.clear()


def _token(client):
    client.post("/api/v1/auth/register", json={"username": "boss", "password": "secret123"})
    r = client.post("/api/v1/auth/login", data={"username": "boss", "password": "secret123"})
    return r.json()["access_token"]


def test_cabinets_requires_auth(client):
    assert client.get("/api/v1/cabinets").status_code == 401


def test_cabinets_empty_then_snapshot(client):
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/v1/cabinets", headers=headers).json() == []

    # Inject a known cabinet directly into the bus snapshot.
    mqtt_module.bus._known_cabinets.add("CAB-001")
    mqtt_module.bus.last_telemetry["CAB-001"] = {"voltage_v": 230.0, "current_a": 2.8}
    mqtt_module.bus.cabinet_state["CAB-001"] = {"relay": "on", "dim": 80}

    data = client.get("/api/v1/cabinets", headers=headers).json()
    assert len(data) == 1
    assert data[0]["cabinet_id"] == "CAB-001"
    assert data[0]["online"] is True
    assert data[0]["state"]["dim"] == 80


def test_create_cabinet_requires_manage(client):
    boss = _token(client)
    client.post(
        "/api/v1/users",
        json={"username": "newbie", "password": "secret123", "rank": "novato"},
        headers={"Authorization": f"Bearer {boss}"},
    )
    newbie = client.post(
        "/api/v1/auth/login", data={"username": "newbie", "password": "secret123"}
    ).json()["access_token"]

    body = {"code": "CAB-009", "name": "Cuadro Test", "latitude": 40.4, "longitude": -3.7}
    blocked = client.post(
        "/api/v1/cabinets/registry", json=body, headers={"Authorization": f"Bearer {newbie}"}
    )
    assert blocked.status_code == 403

    created = client.post(
        "/api/v1/cabinets/registry", json=body, headers={"Authorization": f"Bearer {boss}"}
    )
    assert created.status_code == 201

    # Registered-but-not-reporting cabinet shows up offline, with its location.
    data = client.get("/api/v1/cabinets", headers={"Authorization": f"Bearer {boss}"}).json()
    cab = next(c for c in data if c["cabinet_id"] == "CAB-009")
    assert cab["latitude"] == 40.4
    assert cab["online"] is False


def test_ws_rejects_bad_token(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/v1/ws?token=bad") as ws:
            ws.receive_json()


def test_ws_delivers_snapshot(client):
    token = _token(client)
    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "snapshot"
        assert isinstance(msg["cabinets"], list)
