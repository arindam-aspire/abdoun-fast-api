from __future__ import annotations

import hashlib
import hmac
import os


def _hash_secret_pbkdf2(value: str, salt: str | None = None) -> str:
    effective_salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), effective_salt.encode("utf-8"), 120000)
    return f"pbkdf2_sha256${effective_salt}${digest.hex()}"


def hash_secret(value: str, salt: str | None = None) -> str:
    if salt is None:
        try:
            import bcrypt

            return bcrypt.hashpw(value.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        except ImportError:
            pass
    return _hash_secret_pbkdf2(value, salt)


def verify_secret(value: str, hashed_value: str) -> bool:
    if hashed_value.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            import bcrypt

            return bcrypt.checkpw(value.encode("utf-8"), hashed_value.encode("utf-8"))
        except (ImportError, ValueError):
            return False

    try:
        algorithm, salt, expected = hashed_value.split("$", 2)
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    actual = _hash_secret_pbkdf2(value, salt).split("$", 2)[2]
    return hmac.compare_digest(actual, expected)
