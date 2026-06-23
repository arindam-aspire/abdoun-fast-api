from __future__ import annotations

import hashlib
import hmac
import os


def hash_secret(value: str, salt: str | None = None) -> str:
    effective_salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), effective_salt.encode("utf-8"), 120000)
    return f"pbkdf2_sha256${effective_salt}${digest.hex()}"


def verify_secret(value: str, hashed_value: str) -> bool:
    try:
        algorithm, salt, expected = hashed_value.split("$", 2)
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    actual = hash_secret(value, salt).split("$", 2)[2]
    return hmac.compare_digest(actual, expected)
