"""Licenciamiento atado al equipo (anti-copia para on-premise), con Ed25519.

Una licencia es un token firmado ``<payload_b64>.<firma_b64>`` donde la firma
es **Ed25519(clave_privada, payload_b64)**. El cliente solo lleva la clave
**PÚBLICA** (``settings.license_public_key``): puede *verificar* pero no
*emitir*. Aunque alguien tenga el binario completo, no puede fabricar
licencias — esa es la ventaja sobre HMAC (secreto compartido, extraíble).

- ``machine_fingerprint()``: huella estable del equipo (hostname + MAC).
- ``generate_keypair()`` / ``generate_license()``: las usamos NOSOTROS desde
  ``tools/make_license.py``; la privada nunca se distribuye.
- ``verify_license()`` / ``license_status()``: lo que corre en el cliente.

Sin la clave pública configurada, ``license_status`` informa pero no se
fuerza nada (modo abierto). La política de "qué hacer si la licencia es
inválida" se decide en el arranque/endpoint, no aquí.
"""
import base64
import hashlib
import json
import socket
import time
import uuid

from app.core.config import settings


def _ed25519():
    """Carga PEREZOSA de ``cryptography``. Devuelve ``(InvalidSignature,
    ed25519, serialization)`` o lanza ``RuntimeError`` si la librería no está
    disponible/funcional. Importante: NO se importa a nivel de módulo, para
    que la app no pete al arrancar si la dependencia opcional falla (el
    licenciamiento va apagado por defecto)."""
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import serialization as ser
        from cryptography.hazmat.primitives.asymmetric import ed25519
        return InvalidSignature, ed25519, ser
    except BaseException as exc:  # noqa: BLE001 — incluye PanicException de pyo3
        raise RuntimeError(f"Soporte de cifrado no disponible (cryptography): {exc}") from None


def machine_fingerprint() -> str:
    """Huella estable del equipo: hostname + MAC (uuid.getnode). SHA-256
    truncado a 16 hex para que sea legible al emitir licencias."""
    host = socket.gethostname()
    mac = uuid.getnode()
    raw = f"{host}|{mac}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64d(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


# --- Emisión (uso interno: tools/make_license.py) --------------------------
def generate_keypair() -> tuple[str, str]:
    """Devuelve ``(privada_b64, publica_b64)`` (Ed25519 raw, 32 bytes c/u).
    Genérala UNA vez; guarda la privada a buen recaudo (nunca al cliente)."""
    _, ed25519, ser = _ed25519()
    priv = ed25519.Ed25519PrivateKey.generate()
    priv_b = priv.private_bytes(ser.Encoding.Raw, ser.PrivateFormat.Raw, ser.NoEncryption())
    pub_b = priv.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw)
    return _b64e(priv_b), _b64e(pub_b)


def generate_license(
    *, private_key_b64: str, client: str, fingerprint: str,
    expires_epoch: int | None = None, features: list[str] | None = None,
) -> str:
    """Emite (firma) una licencia. ``fingerprint`` = huella del equipo
    destino, o ``"*"`` para una licencia sin atar (demo/SaaS)."""
    _, ed25519, _ser = _ed25519()
    priv = ed25519.Ed25519PrivateKey.from_private_bytes(_b64d(private_key_b64))
    payload = {
        "client": client,
        "fp": fingerprint,
        "exp": expires_epoch,
        "features": features or ["*"],
        "iat": int(time.time()),
    }
    payload_b64 = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    sig = priv.sign(payload_b64.encode())
    return f"{payload_b64}.{_b64e(sig)}"


# --- Verificación (lo que corre en el cliente) -----------------------------
def verify_license(
    license_str: str | None, *, fingerprint: str | None = None,
    public_key_b64: str | None = None,
) -> tuple[bool, str]:
    """Devuelve ``(válida, motivo)``. Comprueba firma Ed25519 + caducidad +
    huella del equipo. ``public_key_b64`` por defecto la de settings."""
    pub_b64 = public_key_b64 if public_key_b64 is not None else settings.license_public_key
    if not pub_b64:
        return False, "Sin clave pública configurada"
    try:
        InvalidSignature, ed25519, _ser = _ed25519()
    except RuntimeError as exc:
        return False, str(exc)
    try:
        pub = ed25519.Ed25519PublicKey.from_public_bytes(_b64d(pub_b64))
    except Exception:  # noqa: BLE001 — clave mal formada
        return False, "Clave pública inválida"
    if not license_str or "." not in license_str:
        return False, "Sin licencia"
    payload_b64, sig_b64 = license_str.rsplit(".", 1)
    try:
        pub.verify(_b64d(sig_b64), payload_b64.encode())
    except InvalidSignature:
        return False, "Firma inválida"
    except Exception:  # noqa: BLE001 — base64 corrupto, etc.
        return False, "Licencia corrupta"
    try:
        payload = json.loads(_b64d(payload_b64))
    except Exception:  # noqa: BLE001
        return False, "Licencia corrupta"
    exp = payload.get("exp")
    if exp is not None and time.time() > exp:
        return False, "Licencia caducada"
    fp = fingerprint or machine_fingerprint()
    if payload.get("fp") not in ("*", fp):
        return False, "Licencia emitida para otro equipo"
    return True, "OK"


def license_status() -> dict:
    """Estado actual para mostrar en el panel / health."""
    fp = machine_fingerprint()
    if not settings.license_required:
        return {"required": False, "valid": True,
                "reason": "Licencia no requerida (modo abierto)",
                "fingerprint": fp, "client": None}
    valid, reason = verify_license(settings.license_key, fingerprint=fp)
    client = None
    if valid:
        try:
            payload_b64 = settings.license_key.rsplit(".", 1)[0]
            client = json.loads(_b64d(payload_b64)).get("client")
        except Exception:  # noqa: BLE001
            pass
    return {"required": True, "valid": valid, "reason": reason,
            "fingerprint": fp, "client": client}
