"""Password hashing (PBKDF2) and a minimal HS256 JWT signer.

Both use only the standard library so the prototype has no native-crypto
dependency. For production, swap PBKDF2 for bcrypt/argon2 and this hand-rolled
JWT for a vetted library (PyJWT/authlib).
"""
import base64
import hashlib
import hmac
import json
import secrets
import time

from app.core.config import settings

_PBKDF2_ROUNDS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, rounds, salt_hex, digest_hex = stored.split("$")
        salt = bytes.fromhex(salt_hex)
        rounds_int = int(rounds)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, rounds_int)
    return hmac.compare_digest(candidate.hex(), digest_hex)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


class TokenError(Exception):
    pass


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    exp = int(time.time()) + (expires_minutes or settings.access_token_expire_minutes) * 60
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": subject, "exp": exp}
    segments = [
        _b64url_encode(json.dumps(header, separators=(",", ":")).encode()),
        _b64url_encode(json.dumps(payload, separators=(",", ":")).encode()),
    ]
    signing_input = ".".join(segments).encode()
    signature = hmac.new(settings.jwt_secret.encode(), signing_input, hashlib.sha256).digest()
    segments.append(_b64url_encode(signature))
    return ".".join(segments)


def decode_access_token(token: str) -> dict:
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError as exc:
        raise TokenError("Malformed token") from exc

    signing_input = f"{header_b64}.{payload_b64}".encode()
    expected = hmac.new(settings.jwt_secret.encode(), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, _b64url_decode(sig_b64)):
        raise TokenError("Bad signature")

    payload = json.loads(_b64url_decode(payload_b64))
    if payload.get("exp", 0) < int(time.time()):
        raise TokenError("Token expired")
    return payload
