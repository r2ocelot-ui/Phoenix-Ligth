"""TOTP (RFC 6238) implemented on the standard library only.

No pyotp dependency — the algorithm is HMAC-SHA1 over the 30 s time
counter, dynamically truncated to 6 digits. Compatible with Google
Authenticator, Authy, 1Password, etc.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

PERIOD = 30
DIGITS = 6


def generate_secret() -> str:
    """Return a fresh base32 secret (no padding) for a new enrolment."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _hotp(key: bytes, counter: int) -> str:
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** DIGITS)).zfill(DIGITS)


def _key(secret: str) -> bytes | None:
    pad = "=" * ((8 - len(secret) % 8) % 8)
    try:
        return base64.b32decode(secret + pad, casefold=True)
    except Exception:  # noqa: BLE001
        return None


def verify(secret: str | None, code: str | None, window: int = 1) -> bool:
    """Check a 6-digit code, accepting ±``window`` time steps for clock drift."""
    if not secret or not code:
        return False
    code = code.strip().replace(" ", "")
    if not code.isdigit():
        return False
    code = code.zfill(DIGITS)
    key = _key(secret)
    if key is None:
        return False
    now = int(time.time() // PERIOD)
    return any(_hotp(key, now + w) == code for w in range(-window, window + 1))


def provisioning_uri(secret: str, username: str, issuer: str = "Phoenix Light") -> str:
    """otpauth:// URI to encode in a QR or paste into the authenticator app."""
    label = quote(f"{issuer}:{username}")
    return (
        f"otpauth://totp/{label}?secret={secret}"
        f"&issuer={quote(issuer)}&digits={DIGITS}&period={PERIOD}"
    )


# --- Claves de recuperación (backup codes) ---------------------------------
RECOVERY_COUNT = 8


def generate_recovery_codes(n: int = RECOVERY_COUNT) -> list[str]:
    """Genera n claves de recuperación legibles tipo 'A3F9-K2QX'."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin O/0/I/1 para evitar líos
    codes = []
    for _ in range(n):
        raw = "".join(secrets.choice(alphabet) for _ in range(8))
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


def hash_code(code: str) -> str:
    """Hash de una clave de recuperación (normalizada) para guardar en BD."""
    norm = code.strip().upper().replace(" ", "").replace("-", "")
    return hashlib.sha256(norm.encode()).hexdigest()


def verify_recovery(stored_hashes: list[str], code: str) -> str | None:
    """Devuelve el hash que coincide (para que el caller lo consuma) o None."""
    if not stored_hashes or not code:
        return None
    h = hash_code(code)
    return h if h in stored_hashes else None
