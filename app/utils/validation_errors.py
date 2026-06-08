"""Safe serialization of FastAPI/Pydantic validation errors for JSON responses."""

from __future__ import annotations

from typing import Any


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return f"<binary data, {len(value)} bytes>"
    if isinstance(value, dict):
        return {k: _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value


def sanitize_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return validation errors safe for ``jsonable_encoder`` (no raw file bytes)."""
    return [_sanitize_value(dict(err)) for err in errors]
