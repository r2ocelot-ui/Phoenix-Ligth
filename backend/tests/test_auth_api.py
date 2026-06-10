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

    from app.models import audit, device, project, role, security, user  # noqa: F401

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


def _create_user(client, owner_token, username, rank="visualizador", password="secret123"):
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


def _seed_cabinet(code: str = "CAB-001", project_id: int | None = None) -> None:
    """Siembra un Cabinet en BD para que /relay y /dim no caigan en el 404
    del bypass-multi-tenant guard. Sin esto, antes los tests publicaban al
    broker a ciegas; ahora la API exige que el cuadro exista."""
    from app.core.database import get_db
    from app.main import app as _app
    from app.models.cabinet import Cabinet
    db = next(_app.dependency_overrides[get_db]())
    if not db.query(Cabinet).filter(Cabinet.code == code).first():
        db.add(Cabinet(code=code, name=code, project_id=project_id))
        db.commit()


def test_first_user_bootstraps_owner_then_registration_closed(client):
    assert _register(client, "boss").json()["rank"] == "owner"
    # Self-registration is closed once an account exists.
    assert _register(client, "newbie").status_code == 403


def test_admin_creates_users_and_dedups(client):
    _register(client, "boss")
    boss = _token(client, "boss")
    assert _create_user(client, boss, "dup")["rank"] == "visualizador"
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
    assert data["demo_username"] == "phoenix"
    assert data["demo_password"] == "phoenix123"


def test_seeded_demo_admin_can_login(client):
    from app.services.seed import DEMO_PATTERN, DEMO_PIN, seed_demo_admin

    db = next(app.dependency_overrides[get_db]())
    seed_demo_admin(db, "phoenix", "phoenix123")

    # Step 1: username + password + PIN → challenge token (no access token yet,
    # because the seeded admin has a pattern configured).
    r1 = client.post("/api/v1/auth/login",
                     data={"username": "phoenix", "password": "phoenix123", "pin": DEMO_PIN})
    assert r1.status_code == 200, r1.text
    payload = r1.json()
    assert payload["access_token"] is None
    assert payload["challenge_token"]

    # Step 2: challenge + pattern → real JWT.
    r2 = client.post(
        "/api/v1/auth/login/pattern",
        json={"challenge_token": payload["challenge_token"], "pattern": DEMO_PATTERN},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["rank"] == "owner"


def test_novato_blocked_operador_allowed(client):
    _register(client, "boss")
    boss = _token(client, "boss")
    _create_user(client, boss, "newbie", rank="novato")
    newbie = _token(client, "newbie")
    _seed_cabinet()  # /relay exige que el cuadro exista (multi-tenant guard).

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

    _seed_cabinet()
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
    _seed_cabinet()
    client.post("/api/v1/cabinets/CAB-001/dim", json={"level": 50}, headers=_auth(boss))

    r = client.get("/api/v1/audit", headers=_auth(boss))
    assert r.status_code == 200
    actions = {e["action"] for e in r.json()}
    assert {"auth.bootstrap", "auth.login", "cabinet.dim"} <= actions


def _login(client, username, password):
    return client.post("/api/v1/auth/login", data={"username": username, "password": password})


def test_account_locks_after_failed_logins(client):
    # El guard se desactiva por defecto para pruebas; aquí verificamos la
    # lógica del bloqueo, así que lo forzamos a ON durante el test.
    from app.core.config import settings
    settings.lockout_enabled = True
    try:
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
    finally:
        settings.lockout_enabled = False


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


def test_login_step1_returns_jwt_when_no_pattern_set(client):
    # First user gets created without a pattern → step 1 finishes the login
    # immediately, returning the access token.
    _register(client, "boss")
    r = _login(client, "boss", "secret123")
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"], "Expected an access_token when no pattern is configured"
    assert body["challenge_token"] is None


def test_login_requires_both_pin_and_pattern_when_set(client):
    _register(client, "boss")
    boss = _token(client, "boss")
    # Set the full credential stack.
    client.post("/api/v1/auth/pin", json={"pin": "1234"}, headers=_auth(boss))
    client.post("/api/v1/auth/pattern", json={"pattern": "01258"}, headers=_auth(boss))

    # Forgetting the PIN now fails step 1.
    assert _login(client, "boss", "secret123").status_code == 401
    # Wrong PIN fails too.
    r = client.post("/api/v1/auth/login",
                    data={"username": "boss", "password": "secret123", "pin": "9999"})
    assert r.status_code == 401

    # Right password + right PIN → step 1 returns a challenge, not the JWT.
    r1 = client.post("/api/v1/auth/login",
                     data={"username": "boss", "password": "secret123", "pin": "1234"})
    assert r1.status_code == 200
    p = r1.json()
    assert p["access_token"] is None and p["challenge_token"]

    # Wrong pattern in step 2 → 401, right pattern → JWT.
    bad = client.post("/api/v1/auth/login/pattern",
                      json={"challenge_token": p["challenge_token"], "pattern": "8765"})
    assert bad.status_code == 401
    ok = client.post("/api/v1/auth/login/pattern",
                     json={"challenge_token": p["challenge_token"], "pattern": "01258"})
    assert ok.status_code == 200
    assert ok.json()["access_token"]


def test_credential_change_requires_current(client):
    _register(client, "boss")
    boss = _token(client, "boss")
    client.post("/api/v1/auth/pin", json={"pin": "1234"}, headers=_auth(boss))

    # Trying to rotate the PIN without the current one is refused.
    refused = client.post("/api/v1/auth/pin", json={"pin": "5678"}, headers=_auth(boss))
    assert refused.status_code == 401
    # With the current PIN it goes through.
    ok = client.post("/api/v1/auth/pin",
                     json={"pin": "5678", "current_pin": "1234"}, headers=_auth(boss))
    assert ok.status_code == 200


def test_totp_setup_verify_and_login_enforcement(client):
    from app.services import totp as totp_svc
    _register(client, "boss")
    boss = _token(client, "boss")
    # Setup → returns a secret + otpauth URI.
    s = client.post("/api/v1/auth/totp/setup", headers=_auth(boss))
    assert s.status_code == 200
    secret = s.json()["secret"]
    assert s.json()["otpauth_uri"].startswith("otpauth://")
    # A wrong code is rejected.
    bad = client.post("/api/v1/auth/totp/verify", json={"code": "000000"}, headers=_auth(boss))
    assert bad.status_code == 401
    # The right code enables it.
    import time
    code = totp_svc._hotp(totp_svc._key(secret), int(time.time() // 30))
    ok = client.post("/api/v1/auth/totp/verify", json={"code": code}, headers=_auth(boss))
    assert ok.status_code == 200
    assert client.get("/api/v1/auth/me", headers=_auth(boss)).json()["has_totp"] is True
    # Login now routes to a 3rd window: boss has no pattern → step 1 returns a
    # totp challenge (next_step="totp"), and /login/totp finishes it.
    step1 = client.post("/api/v1/auth/login", data={"username": "boss", "password": "secret123"})
    assert step1.status_code == 200
    assert step1.json()["next_step"] == "totp"
    ch = step1.json()["challenge_token"]
    # Wrong code rejected.
    bad_login = client.post("/api/v1/auth/login/totp", json={"challenge_token": ch, "totp": "000000"})
    assert bad_login.status_code == 401
    code2 = totp_svc._hotp(totp_svc._key(secret), int(time.time() // 30))
    ok_login = client.post("/api/v1/auth/login/totp", json={"challenge_token": ch, "totp": code2})
    assert ok_login.status_code == 200 and ok_login.json()["access_token"]
    # Disable clears it.
    assert client.delete("/api/v1/auth/totp", headers=_auth(boss)).status_code == 200
    assert client.get("/api/v1/auth/me", headers=_auth(boss)).json()["has_totp"] is False


def test_totp_recovery_code_login(client):
    from app.services import totp as totp_svc
    import time
    _register(client, "boss")
    boss = _token(client, "boss")
    setup = client.post("/api/v1/auth/totp/setup", headers=_auth(boss)).json()
    # Setup devuelve claves de recuperación legibles.
    assert len(setup["recovery_codes"]) == 8
    rec = setup["recovery_codes"][0]
    code = totp_svc._hotp(totp_svc._key(setup["secret"]), int(time.time() // 30))
    client.post("/api/v1/auth/totp/verify", json={"code": code}, headers=_auth(boss))
    # Login con clave de recuperación (boss sin patrón → ventana totp).
    step1 = client.post("/api/v1/auth/login", data={"username": "boss", "password": "secret123"})
    ch = step1.json()["challenge_token"]
    ok = client.post("/api/v1/auth/login/totp", json={"challenge_token": ch, "totp": rec})
    assert ok.status_code == 200, ok.text
    # La misma clave ya no vale (se consumió).
    step1b = client.post("/api/v1/auth/login", data={"username": "boss", "password": "secret123"})
    again = client.post("/api/v1/auth/login/totp",
                        json={"challenge_token": step1b.json()["challenge_token"], "totp": rec})
    assert again.status_code == 401


def test_admin_can_create_user_with_full_credentials(client):
    _register(client, "boss")
    boss = _token(client, "boss")
    r = client.post("/api/v1/users",
                    json={"username": "alice", "password": "secret123", "rank": "operador",
                          "pin": "4321", "pattern": "0481"},
                    headers=_auth(boss))
    assert r.status_code == 201, r.text
    # Alice now needs the full 2-step flow.
    step1 = client.post("/api/v1/auth/login",
                        data={"username": "alice", "password": "secret123", "pin": "4321"})
    assert step1.status_code == 200 and step1.json()["challenge_token"]
    step2 = client.post("/api/v1/auth/login/pattern",
                        json={"challenge_token": step1.json()["challenge_token"],
                              "pattern": "0481"})
    assert step2.status_code == 200


def test_delete_user_happy_path(client):
    _register(client, "boss")
    boss = _token(client, "boss")
    _create_user(client, boss, "alice", rank="tecnico")
    alice_id = next(u["id"] for u in client.get("/api/v1/users", headers=_auth(boss)).json()
                    if u["username"] == "alice")
    r = client.delete(f"/api/v1/users/{alice_id}", headers=_auth(boss))
    assert r.status_code == 200
    assert all(u["username"] != "alice" for u in client.get("/api/v1/users", headers=_auth(boss)).json())


def test_delete_user_refuses_self(client):
    _register(client, "boss")
    boss = _token(client, "boss")
    boss_id = client.get("/api/v1/auth/me", headers=_auth(boss)).json()["id"]
    r = client.delete(f"/api/v1/users/{boss_id}", headers=_auth(boss))
    assert r.status_code == 403


def test_delete_user_refuses_equal_or_higher_rank(client):
    _register(client, "boss")
    boss = _token(client, "boss")
    # Crear otro owner sería contradictorio porque solo el primero es owner.
    # Probamos con dos admin_proyecto: uno no puede borrar al otro.
    _create_user(client, boss, "ana", rank="admin_proyecto")
    _create_user(client, boss, "bea", rank="admin_proyecto")
    ana = _token(client, "ana")
    bea_id = next(u["id"] for u in client.get("/api/v1/users", headers=_auth(boss)).json()
                  if u["username"] == "bea")
    r = client.delete(f"/api/v1/users/{bea_id}", headers=_auth(ana))
    assert r.status_code == 403


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


def test_ip_ban_blocks_subsequent_requests(client):
    _register(client, "boss")
    boss = _token(client, "boss")
    # Ban the client's IP for an hour.
    r = client.post("/api/v1/security/bans",
                    json={"ip": "testclient", "reason": "pruebas", "minutes": 60},
                    headers=_auth(boss))
    assert r.status_code == 201, r.text
    # Any further request from this IP is 403, including login.
    blocked = client.post("/api/v1/auth/login",
                         data={"username": "boss", "password": "secret123"})
    assert blocked.status_code == 403
    assert "bloqueado" in blocked.json()["detail"].lower()


def test_device_cookie_set_on_login(client):
    _register(client, "boss")
    r = _login(client, "boss", "secret123")
    assert r.status_code == 200
    # The login response should carry the phoenix_device cookie.
    assert any("phoenix_device=" in h for h in r.headers.get_list("set-cookie") if r.headers)


def test_device_revoke_endpoint(client):
    _register(client, "boss")
    boss = _token(client, "boss")
    # The login above already registered a device. List & revoke it.
    devices = client.get("/api/v1/security/devices", headers=_auth(boss)).json()
    assert len(devices) >= 1
    target = devices[0]["device_id"]
    assert client.delete(f"/api/v1/security/devices/{target}",
                         headers=_auth(boss)).status_code == 200
    after = client.get("/api/v1/security/devices", headers=_auth(boss)).json()
    assert all(d["device_id"] != target for d in after)


def test_device_registry_binds_cabinet_and_serial(client):
    from app.core.database import get_db
    from app.main import app as _app
    from app.models.cabinet import Cabinet

    _register(client, "boss")
    boss = _token(client, "boss")
    # Seed two cabinets so the device endpoint can bind to them.
    db = next(_app.dependency_overrides[get_db]())
    db.add(Cabinet(code="CAB-001", name="Test 1"))
    db.add(Cabinet(code="CAB-002", name="Test 2"))
    db.commit()

    r = client.post("/api/v1/devices",
                    json={"cabinet_code": "CAB-001", "serial": "ESP32-AABB", "imei": "353111000000001"},
                    headers=_auth(boss))
    assert r.status_code == 201, r.text
    assert r.json()["serial"] == "ESP32-AABB"
    # Same serial twice → 409.
    again = client.post("/api/v1/devices",
                        json={"cabinet_code": "CAB-002", "serial": "ESP32-AABB"},
                        headers=_auth(boss))
    assert again.status_code == 409


def test_role_editor_lists_seven_default_ranks(client):
    from app.services import role_store
    from app.core.database import get_db
    db = next(app.dependency_overrides[get_db]())
    role_store.seed_default_roles(db)

    _register(client, "boss")
    boss = _token(client, "boss")
    roles = client.get("/api/v1/roles", headers=_auth(boss)).json()
    ids = [r["id"] for r in roles]
    assert "owner" in ids and "visualizador" in ids and len(roles) == 7
    # Owner is flagged protected.
    own = next(r for r in roles if r["id"] == "owner")
    assert own["is_owner"] is True


def test_role_update_changes_effective_permissions(client):
    from app.services import role_store
    from app.core.database import get_db
    db = next(app.dependency_overrides[get_db]())
    role_store.seed_default_roles(db)

    _register(client, "boss")
    boss = _token(client, "boss")
    # Create a técnico — by default cabinet:manage is NOT granted.
    _create_user(client, boss, "newbie", rank="tecnico")
    me = client.get("/api/v1/auth/me",
                    headers=_auth(_token(client, "newbie"))).json()
    assert "cabinet:manage" not in me["permissions"]

    # Owner grants cabinet:manage to the técnico role at the catalogue level.
    upd = client.patch("/api/v1/roles/tecnico",
                       json={"permissions": ["cabinet:read", "cabinet:control",
                                             "alarm:ack", "cabinet:manage"]},
                       headers=_auth(boss))
    assert upd.status_code == 200
    # The técnico we created earlier now has cabinet:manage without changing rank.
    me2 = client.get("/api/v1/auth/me",
                     headers=_auth(_token(client, "newbie"))).json()
    assert "cabinet:manage" in me2["permissions"]


def test_role_editor_protects_owner(client):
    from app.services import role_store
    from app.core.database import get_db
    db = next(app.dependency_overrides[get_db]())
    role_store.seed_default_roles(db)

    _register(client, "boss")
    boss = _token(client, "boss")
    r = client.patch("/api/v1/roles/owner",
                     json={"label": "Sneaky"}, headers=_auth(boss))
    assert r.status_code == 403


def test_role_editor_rejects_privilege_escalation(client):
    from app.services import role_store
    from app.core.database import get_db
    db = next(app.dependency_overrides[get_db]())
    role_store.seed_default_roles(db)

    _register(client, "boss")
    boss = _token(client, "boss")
    # Make alice an admin_proyecto, then bump her to a level low enough to
    # legally edit "tecnico" but not "ingeniero".
    client.post("/api/v1/users",
                json={"username": "alice", "password": "secret123", "rank": "admin_proyecto"},
                headers=_auth(boss))
    # Strip role:manage actually no — admin_proyecto has it by default.
    alice = _token(client, "alice")
    # alice cannot edit roles ≥ her level (admin_proyecto / owner).
    r = client.patch("/api/v1/roles/admin_proyecto",
                     json={"label": "Self-edit"}, headers=_auth(alice))
    assert r.status_code == 403


def test_role_editor_creates_and_uses_custom_role(client):
    from app.services import role_store
    from app.core.database import get_db
    db = next(app.dependency_overrides[get_db]())
    role_store.seed_default_roles(db)

    _register(client, "boss")
    boss = _token(client, "boss")
    cr = client.post("/api/v1/roles",
                     json={"id": "auditor", "label": "Auditor externo",
                           "description": "Sólo lectura con auditoría",
                           "level": 1, "permissions": ["cabinet:read", "audit:read"]},
                     headers=_auth(boss))
    assert cr.status_code == 201
    # Now create a user with that brand-new rank.
    cu = client.post("/api/v1/users",
                     json={"username": "ext", "password": "secret123", "rank": "auditor"},
                     headers=_auth(boss))
    assert cu.status_code == 201
    ext = _token(client, "ext")
    me = client.get("/api/v1/auth/me", headers=_auth(ext)).json()
    assert me["rank"] == "auditor"
    assert "audit:read" in me["permissions"]
    assert "cabinet:control" not in me["permissions"]


def test_project_admin_only_sees_own_users_and_cabinets(client):
    from app.core.database import get_db
    from app.main import app as _app
    from app.models.cabinet import Cabinet
    from app.models.project import Project
    from app.services import role_store
    db = next(_app.dependency_overrides[get_db]())
    role_store.seed_default_roles(db)

    # Two projects with one cabinet each.
    madrid = Project(code="madrid", name="Madrid"); db.add(madrid)
    bcn = Project(code="bcn", name="Barcelona"); db.add(bcn)
    db.commit(); db.refresh(madrid); db.refresh(bcn)
    db.add(Cabinet(code="CAB-MAD", name="Madrid 1", project_id=madrid.id))
    db.add(Cabinet(code="CAB-BCN", name="Barcelona 1", project_id=bcn.id))
    db.commit()

    # Bootstrap owner + admin de cada proyecto.
    _register(client, "owner")
    own = _token(client, "owner")
    client.post("/api/v1/users",
                json={"username": "ana", "password": "secret123", "rank": "admin_proyecto"},
                headers=_auth(own))
    client.post("/api/v1/users",
                json={"username": "bea", "password": "secret123", "rank": "admin_proyecto"},
                headers=_auth(own))
    # Asignar ana → Madrid, bea → Barcelona.
    ana_id = next(u["id"] for u in client.get("/api/v1/users", headers=_auth(own)).json()
                  if u["username"] == "ana")
    bea_id = next(u["id"] for u in client.get("/api/v1/users", headers=_auth(own)).json()
                  if u["username"] == "bea")
    assert client.post("/api/v1/projects/assign-user",
                       json={"user_id": ana_id, "project_id": madrid.id},
                       headers=_auth(own)).status_code == 200
    assert client.post("/api/v1/projects/assign-user",
                       json={"user_id": bea_id, "project_id": bcn.id},
                       headers=_auth(own)).status_code == 200

    # Ana (Madrid) ve solo Madrid: 1 cuadro y solo usuarios de Madrid (ella).
    ana = _token(client, "ana")
    ana_cabs = client.get("/api/v1/cabinets/registry", headers=_auth(ana)).json()
    assert [c["code"] for c in ana_cabs] == ["CAB-MAD"]
    ana_users = client.get("/api/v1/users", headers=_auth(ana)).json()
    assert {u["username"] for u in ana_users} == {"ana"}

    # Bea (Barcelona) ve solo Barcelona.
    bea = _token(client, "bea")
    bea_cabs = client.get("/api/v1/cabinets/registry", headers=_auth(bea)).json()
    assert [c["code"] for c in bea_cabs] == ["CAB-BCN"]

    # Owner ve todos.
    owner_cabs = client.get("/api/v1/cabinets/registry", headers=_auth(own)).json()
    assert {c["code"] for c in owner_cabs} >= {"CAB-MAD", "CAB-BCN"}


def test_project_admin_creates_user_inherits_project(client):
    from app.core.database import get_db
    from app.main import app as _app
    from app.models.project import Project
    from app.services import role_store
    db = next(_app.dependency_overrides[get_db]())
    role_store.seed_default_roles(db)
    p = Project(code="madrid", name="Madrid"); db.add(p); db.commit(); db.refresh(p)

    _register(client, "owner"); own = _token(client, "owner")
    client.post("/api/v1/users",
                json={"username": "ana", "password": "secret123", "rank": "admin_proyecto"},
                headers=_auth(own))
    ana_id = next(u["id"] for u in client.get("/api/v1/users", headers=_auth(own)).json()
                  if u["username"] == "ana")
    client.post("/api/v1/projects/assign-user",
                json={"user_id": ana_id, "project_id": p.id}, headers=_auth(own))

    # Ana crea un técnico — debe heredar project_id=p.id.
    ana = _token(client, "ana")
    r = client.post("/api/v1/users",
                    json={"username": "tom", "password": "secret123", "rank": "tecnico"},
                    headers=_auth(ana))
    assert r.status_code == 201, r.text
    # Ana ve a tom porque ambos están en Madrid.
    visible = client.get("/api/v1/users", headers=_auth(ana)).json()
    assert "tom" in {u["username"] for u in visible}


def test_only_owner_can_manage_projects(client):
    from app.core.database import get_db
    from app.main import app as _app
    from app.services import role_store
    db = next(_app.dependency_overrides[get_db]())
    role_store.seed_default_roles(db)

    _register(client, "owner"); own = _token(client, "owner")
    client.post("/api/v1/users",
                json={"username": "ana", "password": "secret123", "rank": "admin_proyecto"},
                headers=_auth(own))
    ana = _token(client, "ana")
    # Ana intenta crear proyecto → 403.
    r = client.post("/api/v1/projects",
                    json={"code": "sneaky", "name": "Sneaky"}, headers=_auth(ana))
    assert r.status_code == 403


def test_activity_points_accumulate(client):
    _register(client, "boss")
    boss = _token(client, "boss")
    _seed_cabinet()
    client.post("/api/v1/cabinets/CAB-001/dim", json={"level": 10}, headers=_auth(boss))
    me = client.get("/api/v1/auth/me", headers=_auth(boss)).json()
    assert me["activity_points"] >= 1
    assert me["rank"] == "owner"


# --- Ficha del trabajador --------------------------------------------------
def test_admin_edits_worker_profile_and_notes(client):
    _register(client, "boss")
    boss = _token(client, "boss")
    _create_user(client, boss, "curro", rank="tecnico")
    uid = _id_of(client, boss, "curro")

    r = client.patch(
        f"/api/v1/users/{uid}/profile",
        json={
            "full_name": "Curro Jiménez",
            "phone": "+34 600 123 456",
            "job_title": "Técnico de campo",
            "department": "Operaciones",
            "site": "Madrid Sur",
            "shift": "tarde",
            "employee_id": "",
            "national_id": "12345678Z",
            "company": "Iluminaciones García SL",
            "notes": "Disponible para guardias.",
        },
        headers=_auth(boss),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["full_name"] == "Curro Jiménez"
    assert body["national_id"] == "12345678Z"
    assert body["shift"] == "tarde"
    assert body["site"] == "Madrid Sur"
    assert body["company"] == "Iluminaciones García SL"
    # Las notas internas SÍ se devuelven a quien gestiona usuarios.
    assert body["notes"] == "Disponible para guardias."

    # Reabrir la ficha como admin conserva todo.
    detail = client.get(f"/api/v1/users/{uid}", headers=_auth(boss)).json()
    assert detail["company"] == "Iluminaciones García SL"
    assert detail["notes"] == "Disponible para guardias."


def test_profile_notes_hidden_from_self(client):
    """Un usuario NO ve en /auth/me las notas internas que el admin escribió
    sobre él (notes == None), aunque sí ve el resto de su ficha."""
    _register(client, "boss")
    boss = _token(client, "boss")
    _create_user(client, boss, "curro")
    uid = _id_of(client, boss, "curro")
    client.patch(
        f"/api/v1/users/{uid}/profile",
        json={"full_name": "Curro J.", "notes": "Nota confidencial del jefe."},
        headers=_auth(boss),
    )
    curro = _token(client, "curro")
    me = client.get("/api/v1/auth/me", headers=_auth(curro)).json()
    assert me["full_name"] == "Curro J."   # su ficha sí
    assert me["notes"] is None             # las notas internas no


def test_profile_partial_update_keeps_other_fields(client):
    _register(client, "boss")
    boss = _token(client, "boss")
    _create_user(client, boss, "curro")
    uid = _id_of(client, boss, "curro")
    client.patch(f"/api/v1/users/{uid}/profile",
                 json={"full_name": "Curro", "site": "Madrid Sur"}, headers=_auth(boss))
    # Un PATCH posterior que solo toca el teléfono no borra lo anterior.
    client.patch(f"/api/v1/users/{uid}/profile",
                 json={"phone": "+34 911 000 000"}, headers=_auth(boss))
    d = client.get(f"/api/v1/users/{uid}", headers=_auth(boss)).json()
    assert d["full_name"] == "Curro"
    assert d["site"] == "Madrid Sur"
    assert d["phone"] == "+34 911 000 000"


def test_profile_edit_requires_user_manage(client):
    _register(client, "boss")
    boss = _token(client, "boss")
    _create_user(client, boss, "curro", rank="visualizador")
    _create_user(client, boss, "mirona", rank="visualizador")
    uid = _id_of(client, boss, "curro")
    mirona = _token(client, "mirona")  # visualizador: sin user:manage
    r = client.patch(f"/api/v1/users/{uid}/profile",
                     json={"full_name": "Hack"}, headers=_auth(mirona))
    assert r.status_code == 403


def test_last_login_ip_recorded(client):
    _register(client, "boss")
    # Login completo (sin PIN/patrón → un paso) detrás de un proxy simulado.
    r = client.post("/api/v1/auth/login",
                    data={"username": "boss", "password": "secret123"},
                    headers={"X-Forwarded-For": "203.0.113.7"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers=_auth(token)).json()
    assert me["last_login_ip"] == "203.0.113.7"
    assert me["last_login_at"] is not None


# --- 🔴 Seguridad R2 -------------------------------------------------------
def _setup_two_projects(client):
    """Helper: dos proyectos (Madrid, Barcelona) + un cuadro en cada uno.
    Devuelve (owner_token, project_madrid_id, project_bcn_id)."""
    from app.core.database import get_db
    from app.main import app as _app
    from app.models.cabinet import Cabinet
    from app.models.project import Project
    db = next(_app.dependency_overrides[get_db]())
    madrid = Project(code="madrid", name="Madrid"); db.add(madrid)
    bcn = Project(code="bcn", name="Barcelona"); db.add(bcn)
    db.commit(); db.refresh(madrid); db.refresh(bcn)
    db.add(Cabinet(code="CAB-MAD", name="Madrid 1", project_id=madrid.id))
    db.add(Cabinet(code="CAB-BCN", name="Barcelona 1", project_id=bcn.id))
    db.commit()
    _register(client, "owner")
    return _token(client, "owner"), madrid.id, bcn.id


def test_control_blocks_cross_project(client):
    """Bypass multi-tenant en /relay y /dim: un operario asignado a un
    proyecto no puede actuar sobre un cuadro de otro proyecto solo
    conociendo su código. Antes Phoenix solo verificaba el permiso y
    publicaba el comando MQTT a ciegas."""
    own, madrid_id, bcn_id = _setup_two_projects(client)
    client.post("/api/v1/users",
                json={"username": "carlos", "password": "secret123", "rank": "operador"},
                headers=_auth(own))
    carlos_id = _id_of(client, own, "carlos")
    client.post("/api/v1/projects/assign-user",
                json={"user_id": carlos_id, "project_id": madrid_id}, headers=_auth(own))
    carlos = _token(client, "carlos")

    assert client.post("/api/v1/cabinets/CAB-MAD/relay", json={"state": "on"},
                       headers=_auth(carlos)).status_code == 200
    # Cuadro de otra ciudad → 404 (oculto, sin leak de su existencia).
    assert client.post("/api/v1/cabinets/CAB-BCN/relay", json={"state": "on"},
                       headers=_auth(carlos)).status_code == 404
    assert client.post("/api/v1/cabinets/CAB-BCN/dim", json={"level": 50},
                       headers=_auth(carlos)).status_code == 404
    # Inexistente: también 404 (mismo trato).
    assert client.post("/api/v1/cabinets/CAB-INEXIST/relay", json={"state": "on"},
                       headers=_auth(carlos)).status_code == 404


def test_emergency_all_on_scoped_to_project(client):
    """El botón rojo recorría TODO bus._known_cabinets sin filtrar por
    scope: un operario de Madrid podía encender Barcelona. Ahora solo
    afecta a su proyecto; el owner sigue abarcando todos."""
    own, madrid_id, _ = _setup_two_projects(client)
    bus = mqtt_module.bus
    bus._known_cabinets.add("CAB-MAD")
    bus._known_cabinets.add("CAB-BCN")
    try:
        client.post("/api/v1/users",
                    json={"username": "ana", "password": "secret123", "rank": "operador"},
                    headers=_auth(own))
        ana_id = _id_of(client, own, "ana")
        client.post("/api/v1/projects/assign-user",
                    json={"user_id": ana_id, "project_id": madrid_id}, headers=_auth(own))
        ana = _token(client, "ana")
        r = client.post("/api/v1/emergency/all-on", headers=_auth(ana))
        assert r.status_code == 200
        assert r.json()["cabinets"] == ["CAB-MAD"]  # NO CAB-BCN
        # Owner sin filtro abarca todos.
        r = client.post("/api/v1/emergency/all-on", headers=_auth(own))
        assert set(r.json()["cabinets"]) == {"CAB-MAD", "CAB-BCN"}
    finally:
        bus._known_cabinets.discard("CAB-MAD")
        bus._known_cabinets.discard("CAB-BCN")


def test_ws_blocks_inactive_user(client):
    """El WebSocket validaba la firma del token pero no que el usuario
    siguiera activo: un user desactivado podía seguir conectado al feed.
    Ahora se cierra con 4401."""
    from app.core.database import get_db
    from app.main import app as _app
    from app.models.user import User
    db = next(_app.dependency_overrides[get_db]())
    _register(client, "boss")
    boss = _token(client, "boss")
    user = db.query(User).filter(User.username == "boss").first()
    user.is_active = False
    db.commit()
    with pytest.raises(Exception):
        with client.websocket_connect(f"/api/v1/ws?token={boss}") as ws:
            ws.receive_json()


def test_production_safety_blocks_default_secret(monkeypatch):
    """Arrancar con demo_mode=false y jwt_secret en el valor de ejemplo
    es la receta clásica del despliegue inseguro. El guard del lifespan
    debe abortar antes de aceptar peticiones."""
    from app.core.config import settings
    from app.main import DEFAULT_JWT_SECRET, _check_production_safety
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "jwt_secret", DEFAULT_JWT_SECRET)
    monkeypatch.setattr(settings, "lockout_enabled", True)
    with pytest.raises(RuntimeError, match="PHOENIX_JWT_SECRET"):
        _check_production_safety()
    # Con un secreto distinto, no se queja.
    monkeypatch.setattr(settings, "jwt_secret", "una-clave-larga-aleatoria-xxx")
    _check_production_safety()


def test_sun_madrid_summer_solstice():
    """Sanity-check del cálculo astronómico offline. Madrid el solsticio
    de verano 2024: amanece ≈04:44 UTC (06:44 CEST), anochece ≈19:48 UTC
    (21:48 CEST). Tolerancia ±10 min para acomodar el algoritmo simplificado."""
    from datetime import date
    from app.services import sun
    sr = sun.sunrise_utc(date(2024, 6, 21), 40.4168, -3.7038)
    ss = sun.sunset_utc(date(2024, 6, 21), 40.4168, -3.7038)
    assert sr is not None and ss is not None
    # Ventana razonable: alba ~04:44 UTC, ocaso ~19:48 UTC.
    assert 4 * 60 + 30 <= sr.hour * 60 + sr.minute <= 5 * 60
    assert 19 * 60 + 30 <= ss.hour * 60 + ss.minute <= 20 * 60
    assert ss > sr
