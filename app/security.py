from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7
PASSWORD_ITERATIONS = 310_000


def _secret_key() -> bytes:
    key = os.getenv("SECRET_KEY")
    if not key:
        raise RuntimeError("SECRET_KEY must be configured before starting Shop365.")
    return key.encode("utf-8")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, digest_hex = stored_hash.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return hmac.compare_digest(actual, expected)


def create_access_token(user_id: int) -> str:
    expires_at = int(time.time()) + TOKEN_TTL_SECONDS
    payload = f"{user_id}.{expires_at}"
    signature = hmac.new(_secret_key(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def get_token_user_id(token: str) -> int | None:
    try:
        user_id_text, expires_text, signature = token.split(".", 2)
        user_id = int(user_id_text)
        expires_at = int(expires_text)
    except ValueError:
        return None
    if user_id <= 0 or expires_at < int(time.time()):
        return None
    payload = f"{user_id}.{expires_at}"
    expected = hmac.new(_secret_key(), payload.encode(), hashlib.sha256).hexdigest()
    return user_id if hmac.compare_digest(signature, expected) else None
