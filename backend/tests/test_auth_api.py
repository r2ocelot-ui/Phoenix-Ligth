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


def _create_user(client, owner_token, username, rank="novato", password="secret123"):
    r = client.post(
        "/api/v1/users",
        json={"username": username, "password": password, "rank": rank},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _id_of(client, token, username):
    users = client.get("/api/v1/users", headers=_auth(token)).json()
    return next(u["id"] for u in users if u["username"] == username)


def test_first_user_bootstraps_owner_then_registration_closed(client):
    assert _register(client, "boss").json()["rank"] == "owner"
    # Self-registration is closed once an account exists.
    assert _register(client, "newbie").status_code == 403


def test_admin_creates_users_and_dedups(client):
    _register(client, "boss")
    boss = _token(client, "boss")
    assert _create_user(client, boss, "dup")["rank"] == "novato"
    again = client.post(
        "/api/v1/users", json={"username": "dup", "password": "secret123"}, headers=_auth(boss)
    )
    assert again.status_code == 409


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
    boss = _token(client, "boss")
    _create_user(client, boss, "newbie", rank="novato")
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
    boss = _token(client, "boss")
    _create_user(client, boss, "newbie")
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
    boss = _token(client, "boss")
    boss_id = _id_of(client, boss, "boss")
    _create_user(client, boss, "user2", rank="admin")

    # An admin must not be able to promote anyone to owner.
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
    assert {"auth.bootstrap", "auth.login", "cabinet.dim"} <= actions


def _login(client, username, password):
    return client.post("/api/v1/auth/login", data={"username": username, "password": password})


def test_account_locks_after_failed_logins(client):
    _register(client, "boss")
    boss = _token(client, "boss")  # valid session captured before lockout

    # 5 wrong passwords (default threshold) — each rejected with 401.
    for _ in range(5):
        assert _login(client, "boss", "wrong").status_code == 401
    # Now even the *correct* password is refused: the account is locked (429).
    locked = _login(client, "boss", "secret123")
    assert locked.status_code == 429, locked.text

    # The lockout and the failed attempts show up in the admin security feed.
    feed = client.get("/api/v1/audit/security", headers=_auth(boss)).json()
    actions = {e["action"] for e in feed}
    assert "auth.login_failed" in actions
    assert "auth.lockout" in actions


def test_successful_login_resets_failed_counter(client):
    _register(client, "boss")
    # 4 failures stays under the threshold of 5...
    for _ in range(4):
        assert _login(client, "boss", "nope").status_code == 401
    # ...a correct login clears the counter...
    assert _login(client, "boss", "secret123").status_code == 200
    # ...so 4 more failures still don't lock (would be 8 without the reset).
    for _ in range(4):
        assert _login(client, "boss", "nope").status_code == 401
    assert _login(client, "boss", "secret123").status_code == 200


def test_pin_and_pattern_unlock(client):
    _register(client, "boss")
    boss = _token(client, "boss")
    # Set both quick-unlock credentials.
    assert client.post("/api/v1/auth/pin", json={"pin": "1234"}, headers=_auth(boss)).status_code == 200
    assert client.post("/api/v1/auth/pattern", json={"pattern": "0124"}, headers=_auth(boss)).status_code == 200

    me = client.get("/api/v1/auth/me", headers=_auth(boss)).json()
    assert me["has_pin"] and me["has_pattern"]

    # Unlock works with either credential and rotates the token.
    assert client.post("/api/v1/auth/unlock", json={"pin": "1234"}, headers=_auth(boss)).status_code == 200
    assert client.post("/api/v1/auth/unlock", json={"pattern": "0124"}, headers=_auth(boss)).status_code == 200
    # Wrong values are rejected.
    assert client.post("/api/v1/auth/unlock", json={"pin": "9999"}, headers=_auth(boss)).status_code == 401
    assert client.post("/api/v1/auth/unlock", json={"pattern": "8765"}, headers=_auth(boss)).status_code == 401


def test_security_feed_is_admin_only(client):
    _register(client, "boss")
    boss = _token(client, "boss")
    _create_user(client, boss, "sup", rank="supervisor")
    sup = _token(client, "sup")

    # Supervisor has audit:read but not user:manage → security feed is denied.
    assert client.get("/api/v1/audit", headers=_auth(sup)).status_code == 200
    assert client.get("/api/v1/audit/security", headers=_auth(sup)).status_code == 403
    # Owner (wildcard) can read it.
    assert client.get("/api/v1/audit/security", headers=_auth(boss)).status_code == 200


def test_activity_points_accumulate(client):
    _register(client, "boss")
    boss = _token(client, "boss")
    client.post("/api/v1/cabinets/CAB-001/dim", json={"level": 10}, headers=_auth(boss))
    me = client.get("/api/v1/auth/me", headers=_auth(boss)).json()
    assert me["activity_points"] >= 1
    assert me["rank"] == "owner"
