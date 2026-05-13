"""Opaque Remember Me browser tokens (high entropy) and stable DB hashes."""
from __future__ import annotations

import hashlib
import secrets

from app.utils.constants import RememberMeConstants


def generate_opaque_remember_me_token() -> str:
    return secrets.token_urlsafe(RememberMeConstants.OPAQUE_TOKEN_NUM_BYTES)


def hash_remember_me_opaque_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
