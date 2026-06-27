from __future__ import annotations

import hashlib
import hmac
import secrets


ITERATIONS = 210_000


def create_password_hash(password: str) -> tuple[str, str]:
    """Return salt and PBKDF2-HMAC-SHA256 password hash."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        ITERATIONS,
    ).hex()
    return salt, digest


def verify_password(password: str, salt: str, password_hash: str) -> bool:
    candidate = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        ITERATIONS,
    ).hex()
    return hmac.compare_digest(candidate, password_hash)
