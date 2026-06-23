from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.core.config import get_settings


def _b64encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _b64decode(payload: str) -> bytes:
    padded = payload + "=" * ((4 - len(payload) % 4) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def create_token(
    *,
    subject: str,
    token_type: str,
    expires_in_seconds: int,
    role_name: str | None = None,
    roles: list[str] | None = None,
) -> str:
    settings = get_settings()
    header = {"alg": "HS256", "typ": "JWT"}
    payload: dict[str, Any] = {
        "sub": subject,
        "typ": token_type,
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in_seconds,
    }
    if role_name:
        payload["role"] = {"role_name": role_name}
    if roles:
        payload["roles"] = roles

    signing_input = f"{_b64encode(json.dumps(header, separators=(',', ':')).encode())}.{_b64encode(json.dumps(payload, separators=(',', ':')).encode())}"
    signature = hmac.new(
        settings.auth_token_secret.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_b64encode(signature)}"


def verify_token(token: str, *, expected_type: str | None = None) -> dict[str, Any] | None:
    settings = get_settings()
    try:
        header_segment, payload_segment, signature_segment = token.split(".", 2)
    except ValueError:
        return None

    signing_input = f"{header_segment}.{payload_segment}"
    expected_signature = hmac.new(
        settings.auth_token_secret.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(_b64encode(expected_signature), signature_segment):
        return None

    try:
        payload = json.loads(_b64decode(payload_segment))
    except (json.JSONDecodeError, ValueError):
        return None

    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    if expected_type and payload.get("typ") != expected_type:
        return None
    return payload
