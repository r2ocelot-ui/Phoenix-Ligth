"""Licenciamiento atado al equipo (anti-copia para despliegues on-premise).

Una licencia es un token firmado: ``<payload_b64>.<firma_b64>`` donde la
firma es HMAC-SHA256(secreto, payload). El payload lleva el cliente, la
huella del equipo permitida, la caducidad opcional y las funciones.

- ``machine_fingerprint()``: huella estable del servidor (hostname + MAC).
- ``verify_license()``: comprueba firma + huella + caducidad.
- ``generate_license()``: la usamos NOSOTROS (tools/make_license.py) para
  emitir licencias; no se expone por la API.

Nota de seguridad: HMAC es simétrico (el secreto va en el binario
compilado, ofuscado). Para máxima dureza migrar a Ed25519 (lib
``cryptography``) — documentado en docs/DECISIONS.md. Para evitar copias
casuales e instalaciones no autorizadas, HMAC + fingerprint cumple.
"""
import base64
import hashlib
import hmac
import json
import socket
import time
import uuid

from app.core.config import settings


def machine_fingerprint() -> str:
    """Huella estable del equipo: hostname + MAC (uuid.getnode). SHA-256
    truncado a 16 hex para que sea legible al emitir licencias."""
    host = socket.gethostname()
    mac = uuid.getnode()
    raw = f"{host}|{mac}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def _sign(payload_b64: str) -> str:
    sig = hmac.new(settings.license_secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=")


def generate_license(
    *, client: str, fingerprint: str, expires_epoch: int | None = None,
    features: list[str] | None = None,
) -> str:
    """Emite una licencia firmada. ``fingerprint`` = huella del equipo
    destino, o "*" para una licencia sin atar (p.ej. demo/SaaS)."""
    payload = {
        "client": client,
        "fp": fingerprint,
        "exp": expires_epoch,
        "features": features or ["*"],
        "iat": int(time.time()),
    }
    payload_b64 = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    return f"{payload_b64}.{_sign(payload_b64)}"


def _b64_pad(s: str) -> str:
    return s + "=" * ((4 - len(s) % 4) % 4)


def verify_license(license_str: str | None, *, fingerprint: str | None = None) -> tuple[bool, str]:
    """Devuelve (válida, motivo). ``fingerprint`` por defecto el del equipo."""
    if not license_str or "." not in license_str:
        return False, "Sin licencia"
    payload_b64, sig = license_str.rsplit(".", 1)
    # Firma (comparación en tiempo constante).
    if not hmac.compare_digest(sig, _sign(payload_b64)):
        return False, "Firma inválida"
    try:
        payload = json.loads(base64.urlsafe_b64decode(_b64_pad(payload_b64)))
    except Exception:  # noqa: BLE001
        return False, "Licencia corrupta"
    # Caducidad.
    exp = payload.get("exp")
    if exp is not None and time.time() > exp:
        return False, "Licencia caducada"
    # Huella del equipo (a no ser que la licencia sea comodín "*").
    fp = fingerprint or machine_fingerprint()
    lic_fp = payload.get("fp")
    if lic_fp not in ("*", fp):
        return False, "Licencia emitida para otro equipo"
    return True, "OK"


def license_status() -> dict:
    """Estado actual para mostrar en el panel / health."""
    fp = machine_fingerprint()
    if not settings.license_required:
        return {"required": False, "valid": True, "reason": "Licencia no requerida (modo abierto)", "fingerprint": fp}
    valid, reason = verify_license(settings.license_key, fingerprint=fp)
    client = None
    if valid:
        try:
            payload_b64 = settings.license_key.rsplit(".", 1)[0]
            client = json.loads(base64.urlsafe_b64decode(_b64_pad(payload_b64))).get("client")
        except Exception:  # noqa: BLE001
            pass
    return {"required": True, "valid": valid, "reason": reason, "fingerprint": fp, "client": client}
