import app.core.mqtt_client as mqtt_module
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
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    from app.models import audit, user  # noqa: F401 - register tables

    Base.metadata.create_all(engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Stub the MQTT publish so control endpoints don't need a live broker.
    async def _noop(*args, **kwargs):
        return None

    original_publish = mqtt_module.bus.publish
    mqtt_module.bus.publish = _noop

    # No `with` block: skip lifespan so the real MQTT bus / DB don't start.
    yield TestClient(app)

    mqtt_module.bus.publish = original_publish
    app.dependency_overrides.clear()


def _register(client, username, password="secret123"):
    return client.post(
        "/api/v1/auth/register", json={"username": username, "password": password}
    )


def _token(client, username, password="secret123"):
    r = client.post(
        "/api/v1/auth/login", data={"username": username, "password": password}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _id_of(client, token, username):
    users = client.get("/api/v1/users", headers=_auth(token)).json()
    return next(u["id"] for u in users if u["username"] == username)


def test_first_user_is_owner_rest_are_novato(client):
    assert _register(client, "boss").json()["rank"] == "owner"
    assert _register(client, "newbie").json()["rank"] == "novato"


def test_duplicate_username_rejected(client):
    _register(client, "boss")
    assert _register(client, "boss").status_code == 409


def test_unauthenticated_requests_are_rejected(client):
    assert client.get("/api/v1/users").status_code == 401
    assert client.post("/api/v1/cabinets/CAB-1/relay", json={"state": "on"}).status_code == 401


def test_auth_info_reveals_demo_credentials(client):
    data = client.get("/api/v1/auth/info").json()
    assert data["demo_mode"] is True
    assert data["demo_username"] == "admin"
    assert data["demo_password"] == "phoenix123"


def test_seeded_demo_admin_can_login(client):
    from app.services.seed import seed_demo_admin

    # Seed through the same overridden session the app uses.
    db = next(app.dependency_overrides[get_db]())
    seed_demo_admin(db, "admin", "phoenix123")

    r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "phoenix123"})
    assert r.status_code == 200
    assert r.json()["rank"] == "owner"


def test_novato_blocked_operador_allowed(client):
    _register(client, "boss")
    _register(client, "newbie")
    boss = _token(client, "boss")
    newbie = _token(client, "newbie")

    blocked = client.post(
        "/api/v1/cabinets/CAB-001/relay", json={"state": "on"}, headers=_auth(newbie)
    )
    assert blocked.status_code == 403

    nid = _id_of(client, boss, "newbie")
    assert (
        client.post(
            f"/api/v1/users/{nid}/rank", json={"rank": "operador"}, headers=_auth(boss)
        ).status_code
        == 200
    )

    allowed = client.post(
        "/api/v1/cabinets/CAB-001/relay", json={"state": "on"}, headers=_auth(newbie)
    )
    assert allowed.status_code == 200, allowed.text


def test_per_user_permission_override_grants_control(client):
    _register(client, "boss")
    _register(client, "newbie")
    boss = _token(client, "boss")
    newbie = _token(client, "newbie")
    nid = _id_of(client, boss, "newbie")

    r = client.post(
        f"/api/v1/users/{nid}/permissions",
        json={"extra_permissions": ["cabinet:control"], "denied_permissions": []},
        headers=_auth(boss),
    )
    assert r.status_code == 200
    assert "cabinet:control" in r.json()["permissions"]

    granted = client.post(
        "/api/v1/cabinets/CAB-001/dim", json={"level": 40}, headers=_auth(newbie)
    )
    assert granted.status_code == 200, granted.text


def test_cannot_assign_rank_above_own(client):
    _register(client, "boss")
    _register(client, "user2")
    boss = _token(client, "boss")
    boss_id = _id_of(client, boss, "boss")
    user2_id = _id_of(client, boss, "user2")

    # Make user2 an admin; an admin must not be able to make anyone owner.
    client.post(f"/api/v1/users/{user2_id}/rank", json={"rank": "admin"}, headers=_auth(boss))
    user2 = _token(client, "user2")
    r = client.post(
        f"/api/v1/users/{boss_id}/rank", json={"rank": "owner"}, headers=_auth(user2)
    )
    assert r.status_code == 403


def test_audit_log_records_actions(client):
    _register(client, "boss")
    boss = _token(client, "boss")
    client.post("/api/v1/cabinets/CAB-001/dim", json={"level": 50}, headers=_auth(boss))

    r = client.get("/api/v1/audit", headers=_auth(boss))
    assert r.status_code == 200
    actions = {e["action"] for e in r.json()}
    assert {"auth.register", "auth.login", "cabinet.dim"} <= actions


def test_activity_points_accumulate(client):
    _register(client, "boss")
    boss = _token(client, "boss")
    client.post("/api/v1/cabinets/CAB-001/dim", json={"level": 10}, headers=_auth(boss))
    me = client.get("/api/v1/auth/me", headers=_auth(boss)).json()
    assert me["activity_points"] >= 1
    assert me["rank"] == "owner"
