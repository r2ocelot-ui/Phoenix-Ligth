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


def test_emergency_partial_scope_only_affects_listed(client, monkeypatch):
    """Emergencia POR CM: con body {cabinet_codes:[…]} solo se fuerzan esos.
    Defensa: incluir un CM fuera del scope NO lo afecta — la intersección
    con la tenencia se hace siempre en backend."""
    H = {"Authorization": f"Bearer {_token(client)}"}
    for code in ("CAB-P1", "CAB-P2", "CAB-P3"):
        client.post("/api/v1/cabinets/registry", json={"code": code}, headers=H)
        client.post(f"/api/v1/cabinets/{code}/mode", json={"mode": "ai"}, headers=H)
    mqtt_module.bus._known_cabinets.update({"CAB-P1", "CAB-P2", "CAB-P3"})
    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(mqtt_module.bus, "publish", _noop)
    monkeypatch.setattr(mqtt_module.bus, "_safe_publish", _noop)

    # Solo CAB-P1: el resto sigue en su modo (ai).
    r = client.post(
        "/api/v1/emergency/all-on",
        json={"cabinet_codes": ["CAB-P1", "CAB-NOPE"]},
        headers=H,
    )
    assert r.status_code == 200
    affected = set(r.json()["cabinets"])
    assert affected == {"CAB-P1"}  # 'CAB-NOPE' ignorado (fuera de scope/no existe)
    data = {c["cabinet_id"]: c for c in client.get("/api/v1/cabinets", headers=H).json()}
    assert data["CAB-P1"]["dimming_mode"] == "manual"
    assert data["CAB-P2"]["dimming_mode"] == "ai"
    assert data["CAB-P3"]["dimming_mode"] == "ai"
    # status sigue diciendo "activa", solo con CAB-P1.
    st = client.get("/api/v1/emergency/status", headers=H).json()
    assert st["active"] is True and st["cabinets"] == ["CAB-P1"]

    # /clear con scope también respeta la lista (limpia solo CAB-P1).
    r2 = client.post(
        "/api/v1/emergency/clear",
        json={"cabinet_codes": ["CAB-P1"]},
        headers=H,
    )
    assert {c["code"]: c["mode"] for c in r2.json()["cabinets"]} == {"CAB-P1": "ai"}
    assert client.get("/api/v1/emergency/status", headers=H).json()["active"] is False


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


def test_lightpoints_import_requires_data_transfer(client):
    """El import de luminarias está reservado a ingeniero+ (permiso
    data:transfer). Un operador (que sí puede gestionar topología clásica si
    se la dan, pero NO transferir datos en bloque) recibe 403; un ingeniero
    completa la operación sin que el backend la rechace por permiso.
    Defensa explícita del backlog del 14-jun: subir/bajar inventario en
    bloque solo desde rangos altos."""
    boss = _token(client)
    # Creamos el CM con el owner.
    client.post(
        "/api/v1/cabinets/registry",
        json={"code": "CAB-PERM"},
        headers={"Authorization": f"Bearer {boss}"},
    )

    # Operador (sin data:transfer) → 403.
    client.post(
        "/api/v1/users",
        json={"username": "op1", "password": "secret123", "rank": "operador"},
        headers={"Authorization": f"Bearer {boss}"},
    )
    op = client.post(
        "/api/v1/auth/login",
        data={"username": "op1", "password": "secret123"},
    ).json()["access_token"]
    csv_body = "Nº,CM,Fase,W\r\n1,CAB-PERM,L1,80\r\n"
    blocked = client.post(
        "/api/v1/lightpoints/import",
        json={"csv": csv_body},
        headers={"Authorization": f"Bearer {op}"},
    )
    assert blocked.status_code == 403

    # Ingeniero (con data:transfer por defecto) → 200.
    client.post(
        "/api/v1/users",
        json={"username": "ing1", "password": "secret123", "rank": "ingeniero"},
        headers={"Authorization": f"Bearer {boss}"},
    )
    ing = client.post(
        "/api/v1/auth/login",
        data={"username": "ing1", "password": "secret123"},
    ).json()["access_token"]
    ok = client.post(
        "/api/v1/lightpoints/import",
        json={"csv": csv_body},
        headers={"Authorization": f"Bearer {ing}"},
    )
    assert ok.status_code == 200
    assert ok.json()["created"] == 1


def test_backup_restore_cabinet_roundtrip(client):
    """Backup JSON de un CM completo → restore en otro CM → topología
    idéntica (circuitos + luminarias). Un segundo restore es idempotente
    (no duplica). Gateado por data:transfer (operador → 403)."""
    boss = _token(client)
    H = {"Authorization": f"Bearer {boss}"}
    # CM origen: 2 circuitos, 3 luminarias.
    client.post("/api/v1/cabinets/registry", json={
        "code": "CAB-SRC", "name": "Origen", "latitude": 40.4, "longitude": -3.7,
    }, headers=H)
    client.post("/api/v1/circuits", json={
        "cabinet_code": "CAB-SRC", "number": 1, "name": "Salida 1", "phase": "L1",
    }, headers=H)
    client.post("/api/v1/circuits", json={
        "cabinet_code": "CAB-SRC", "number": 2, "name": "Salida 2", "phase": "L2",
    }, headers=H)
    circuits = client.get("/api/v1/circuits?cabinet_code=CAB-SRC", headers=H).json()
    c1 = next(c for c in circuits if c["number"] == 1)
    c2 = next(c for c in circuits if c["number"] == 2)
    client.post("/api/v1/lightpoints", json={
        "cabinet_code": "CAB-SRC", "circuit_id": c1["id"], "number": 1,
        "label": "Farola 01", "phase": "L1", "power_w": 80.0,
        "street": "Calle Mayor",
    }, headers=H)
    client.post("/api/v1/lightpoints", json={
        "cabinet_code": "CAB-SRC", "circuit_id": c1["id"], "number": 2,
        "label": "Farola 02", "phase": "L1", "power_w": 90.0,
    }, headers=H)
    client.post("/api/v1/lightpoints", json={
        "cabinet_code": "CAB-SRC", "circuit_id": c2["id"], "number": 3,
        "label": "Farola 03", "phase": "L2", "power_w": 100.0,
    }, headers=H)

    # Backup.
    backup = client.get("/api/v1/cabinets/CAB-SRC/backup", headers=H)
    assert backup.status_code == 200
    payload = backup.json()
    assert payload["schema_version"] == 1
    assert payload["cabinet"]["code"] == "CAB-SRC"
    assert {c["number"] for c in payload["circuits"]} == {1, 2}
    assert {p["number"] for p in payload["lightpoints"]} == {1, 2, 3}
    # Cada luminaria lleva el número de su circuito, no un id transitorio.
    p1 = next(p for p in payload["lightpoints"] if p["number"] == 1)
    assert p1["circuit_number"] == 1 and p1["power_w"] == 80.0

    # CM destino (vacío, distinto código → backup como plantilla).
    client.post("/api/v1/cabinets/registry", json={
        "code": "CAB-DST", "name": "Destino",
    }, headers=H)
    res = client.post("/api/v1/cabinets/CAB-DST/restore", json=payload, headers=H)
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["circuits_created"] == 2 and out["lp_created"] == 3
    assert out["circuits_updated"] == 0 and out["lp_updated"] == 0
    assert out["errors"] == []

    # Topología clonada: mismos circuitos y luminarias en el destino.
    pts = client.get("/api/v1/lightpoints?cabinet_code=CAB-DST", headers=H).json()
    assert {p["number"] for p in pts} == {1, 2, 3}
    assert next(p for p in pts if p["number"] == 1)["power_w"] == 80.0

    # Restore idempotente: re-aplicar el mismo JSON solo actualiza.
    res2 = client.post("/api/v1/cabinets/CAB-DST/restore", json=payload, headers=H)
    out2 = res2.json()
    assert out2["circuits_created"] == 0 and out2["lp_created"] == 0
    assert out2["circuits_updated"] == 2 and out2["lp_updated"] == 3


def test_backup_restore_require_data_transfer(client):
    """Los endpoints conjunto/backup están reservados a ingeniero+. Un
    operador no llega ni a leer (defensa en profundidad: el inventario
    podría ser sensible)."""
    boss = _token(client)
    H = {"Authorization": f"Bearer {boss}"}
    client.post("/api/v1/cabinets/registry", json={"code": "CAB-GATE"}, headers=H)
    # Operador sin data:transfer.
    client.post("/api/v1/users", json={
        "username": "op2", "password": "secret123", "rank": "operador",
    }, headers=H)
    op = client.post(
        "/api/v1/auth/login", data={"username": "op2", "password": "secret123"},
    ).json()["access_token"]
    Hop = {"Authorization": f"Bearer {op}"}
    assert client.get("/api/v1/cabinets/CAB-GATE/backup", headers=Hop).status_code == 403
    assert client.post(
        "/api/v1/cabinets/CAB-GATE/restore",
        json={"schema_version": 1, "circuits": [], "lightpoints": []},
        headers=Hop,
    ).status_code == 403


def test_restore_rejects_future_schema_version(client):
    """Defensa contra archivos que vengan de una versión más nueva del
    formato — antes que aceptar a medias, paramos con 422."""
    boss = _token(client)
    H = {"Authorization": f"Bearer {boss}"}
    client.post("/api/v1/cabinets/registry", json={"code": "CAB-VER"}, headers=H)
    bad = client.post(
        "/api/v1/cabinets/CAB-VER/restore",
        json={"schema_version": 999, "circuits": [], "lightpoints": []},
        headers=H,
    )
    assert bad.status_code == 422
    assert "schema_version" in bad.text


def test_lightpoints_csv_import_upsert(client):
    """Importar CSV de luminarias: crea, luego actualiza por (CM, Nº) sin
    duplicar, y una fila con CM inexistente avisa sin romper el resto."""
    headers = {"Authorization": f"Bearer {_token(client)}"}
    client.post("/api/v1/cabinets/registry", json={"code": "CAB-IMP"}, headers=headers)
    csv1 = (
        "Nº,Calle,Nº calle,Localidad,Provincia,CP,CM,Circuito,Fase,Fabricante,Modelo,W,Inventario,Tecnología\r\n"
        "1,Calle Mayor,5,Madrid,Madrid,28013,CAB-IMP,1,L1,Schreder,Z1,80,INV-1,LED\r\n"
        "2,,,,,,CAB-IMP,1,L2,,,100,,\r\n"
    )
    r = client.post("/api/v1/lightpoints/import", json={"csv": csv1}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 2 and r.json()["updated"] == 0
    # Reimport con cambio → UPDATE, no duplica.
    csv2 = "Nº,Calle,CM,Circuito,Fase,W\r\n1,Calle Mayor Reformada,CAB-IMP,1,L1,90\r\n"
    r2 = client.post("/api/v1/lightpoints/import", json={"csv": csv2}, headers=headers)
    assert r2.json()["updated"] == 1 and r2.json()["created"] == 0
    pts = client.get("/api/v1/lightpoints?cabinet_code=CAB-IMP", headers=headers).json()
    assert len(pts) == 2  # no duplicó
    p1 = next(p for p in pts if p["number"] == 1)
    assert p1["street"] == "Calle Mayor Reformada" and p1["power_w"] == 90
    # CM inexistente → aviso en esa fila, no rompe.
    r3 = client.post("/api/v1/lightpoints/import", json={"csv": "Nº,CM\r\n1,CAB-NOPE\r\n"}, headers=headers)
    assert r3.status_code == 200 and r3.json()["created"] == 0 and len(r3.json()["errors"]) == 1
