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
    from app.models import audit, device, role, security, user  # noqa: F401

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


def test_security_headers_present(client):
    """La CSP estricta debe llegar en cada respuesta junto al resto de
    cabeceras de seguridad. Si alguna se pierde por un cambio del middleware,
    se nota aquí antes de salir a producción."""
    r = client.get("/health")
    assert r.status_code == 200
    csp = r.headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'self'" in csp
    # script-src no puede ser 'unsafe-inline' (eso anula la defensa anti-XSS).
    assert "'unsafe-inline'" not in csp.split("script-src", 1)[1].split(";", 1)[0]
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "SAMEORIGIN"
    assert r.headers.get("referrer-policy") == "no-referrer"


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


def test_set_mode_ai_persists(client):
    headers = {"Authorization": f"Bearer {_token(client)}"}
    body = {"code": "CAB-AI", "name": "AI", "latitude": 40.4, "longitude": -3.7}
    assert client.post("/api/v1/cabinets/registry", json=body, headers=headers).status_code == 201
    r = client.post("/api/v1/cabinets/CAB-AI/mode", json={"mode": "ai"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["mode"] == "ai"
    # 'level' es int (de noche) o 0 (de día): no asumimos la hora del test.
    assert r.json()["level"] is None or isinstance(r.json()["level"], int)
    data = client.get("/api/v1/cabinets", headers=headers).json()
    cab = next(c for c in data if c["cabinet_id"] == "CAB-AI")
    assert cab["dimming_mode"] == "ai"
    assert cab["street_profile"] == "residential"


def test_set_mode_rejects_invalid(client):
    headers = {"Authorization": f"Bearer {_token(client)}"}
    client.post("/api/v1/cabinets/registry", json={"code": "CAB-M"}, headers=headers)
    bad = client.post("/api/v1/cabinets/CAB-M/mode", json={"mode": "turbo"}, headers=headers)
    assert bad.status_code == 422


def test_dim_switches_cabinet_to_manual(client, monkeypatch):
    headers = {"Authorization": f"Bearer {_token(client)}"}
    client.post(
        "/api/v1/cabinets/registry",
        json={"code": "CAB-D", "latitude": 40.4, "longitude": -3.7},
        headers=headers,
    )
    client.post("/api/v1/cabinets/CAB-D/mode", json={"mode": "ai"}, headers=headers)
    # No hay broker en test → publish lanzaría RuntimeError (503). Lo mockeamos.
    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(mqtt_module.bus, "publish", _noop)
    r = client.post("/api/v1/cabinets/CAB-D/dim", json={"level": 10}, headers=headers)
    assert r.status_code == 200
    assert r.json()["mode"] == "manual"
    data = client.get("/api/v1/cabinets", headers=headers).json()
    cab = next(c for c in data if c["cabinet_id"] == "CAB-D")
    assert cab["dimming_mode"] == "manual"


def test_emergency_remembers_and_restores_mode(client, monkeypatch):
    """Ciclo de emergencia: /all-on guarda el modo previo y pone manual.
    /clear restaura ese modo (ai/schedule) y limpia pre_emergency_mode."""
    headers = {"Authorization": f"Bearer {_token(client)}"}
    # Dos cuadros con modos distintos para demostrar que cada uno conserva el suyo.
    client.post("/api/v1/cabinets/registry", json={"code": "CAB-E1", "latitude": 40.4, "longitude": -3.7}, headers=headers)
    client.post("/api/v1/cabinets/registry", json={"code": "CAB-E2"}, headers=headers)
    client.post("/api/v1/cabinets/CAB-E1/mode", json={"mode": "ai"}, headers=headers)
    client.post("/api/v1/cabinets/CAB-E2/mode", json={"mode": "schedule"}, headers=headers)
    # Inyecta los cuadros en el bus (la emergencia solo afecta a los "known").
    mqtt_module.bus._known_cabinets.update({"CAB-E1", "CAB-E2"})
    # No hay broker en test → mockeamos publish y safe_publish.
    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(mqtt_module.bus, "publish", _noop)
    monkeypatch.setattr(mqtt_module.bus, "_safe_publish", _noop)

    # /emergency/status: no hay emergencia activa.
    assert client.get("/api/v1/emergency/status", headers=headers).json()["active"] is False

    # Activar emergencia.
    r = client.post("/api/v1/emergency/all-on", headers=headers)
    assert r.status_code == 200
    affected = set(r.json()["cabinets"])
    assert {"CAB-E1", "CAB-E2"}.issubset(affected)
    data = {c["cabinet_id"]: c for c in client.get("/api/v1/cabinets", headers=headers).json()}
    assert data["CAB-E1"]["dimming_mode"] == "manual"
    assert data["CAB-E2"]["dimming_mode"] == "manual"
    assert client.get("/api/v1/emergency/status", headers=headers).json()["active"] is True

    # Activarla de NUEVO no debe pisar el modo previo guardado.
    client.post("/api/v1/emergency/all-on", headers=headers)

    # Apagar emergencia → cada cuadro vuelve a SU modo previo.
    r = client.post("/api/v1/emergency/clear", headers=headers)
    assert r.status_code == 200
    restored = {c["code"]: c["mode"] for c in r.json()["cabinets"]}
    assert restored["CAB-E1"] == "ai"
    assert restored["CAB-E2"] == "schedule"
    data = {c["cabinet_id"]: c for c in client.get("/api/v1/cabinets", headers=headers).json()}
    assert data["CAB-E1"]["dimming_mode"] == "ai"
    assert data["CAB-E2"]["dimming_mode"] == "schedule"
    # Y status vuelve a "no activa".
    assert client.get("/api/v1/emergency/status", headers=headers).json()["active"] is False
    # Idempotente: un /clear de más no rompe nada.
    assert client.post("/api/v1/emergency/clear", headers=headers).status_code == 200


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
