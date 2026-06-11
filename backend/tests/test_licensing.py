"""Licenciamiento Ed25519 (funciones puras, sin servidor)."""
import base64
import json
import time

import pytest

from app.services import licensing

# Si ``cryptography`` no está funcional en el entorno (p.ej. falta el backend
# nativo), se saltan estos tests en vez de fallar — la app sigue arrancando
# porque el import es perezoso y el licenciamiento va apagado por defecto.
try:
    licensing.generate_keypair()
    _CRYPTO_OK = True
except Exception:  # noqa: BLE001
    _CRYPTO_OK = False

pytestmark = pytest.mark.skipif(not _CRYPTO_OK, reason="cryptography/Ed25519 no funcional aquí")


def _mint(priv, **kw):
    kw.setdefault("client", "Ayto X")
    kw.setdefault("fingerprint", "*")
    return licensing.generate_license(private_key_b64=priv, **kw)


def test_keypair_sign_verify_roundtrip():
    priv, pub = licensing.generate_keypair()
    lic = _mint(priv)
    ok, reason = licensing.verify_license(lic, fingerprint="abc123", public_key_b64=pub)
    assert ok, reason


def test_wrong_public_key_is_invalid_signature():
    priv, _ = licensing.generate_keypair()
    _, other_pub = licensing.generate_keypair()
    ok, reason = licensing.verify_license(_mint(priv), public_key_b64=other_pub)
    assert not ok and reason == "Firma inválida"


def test_expired_license():
    priv, pub = licensing.generate_keypair()
    lic = _mint(priv, expires_epoch=int(time.time()) - 10)
    ok, reason = licensing.verify_license(lic, public_key_b64=pub)
    assert not ok and reason == "Licencia caducada"


def test_fingerprint_binding():
    priv, pub = licensing.generate_keypair()
    lic = _mint(priv, fingerprint="machine-AAA")
    assert licensing.verify_license(lic, fingerprint="machine-AAA", public_key_b64=pub)[0]
    ok, reason = licensing.verify_license(lic, fingerprint="machine-BBB", public_key_b64=pub)
    assert not ok and reason == "Licencia emitida para otro equipo"


def test_tampered_payload_is_rejected():
    priv, pub = licensing.generate_keypair()
    _, sig = _mint(priv).rsplit(".", 1)
    forged = json.dumps({"client": "HACK", "fp": "*", "exp": None, "features": ["*"], "iat": 0})
    forged_b64 = base64.urlsafe_b64encode(forged.encode()).decode().rstrip("=")
    ok, _reason = licensing.verify_license(f"{forged_b64}.{sig}", public_key_b64=pub)
    assert not ok  # la firma no cuadra con el payload alterado


def test_no_public_key_means_open_mode():
    ok, reason = licensing.verify_license("whatever.sig", public_key_b64="")
    assert not ok and "pública" in reason


def test_wildcard_fingerprint_works_on_any_machine():
    priv, pub = licensing.generate_keypair()
    lic = _mint(priv, fingerprint="*")
    assert licensing.verify_license(lic, fingerprint="cualquier-cosa", public_key_b64=pub)[0]
