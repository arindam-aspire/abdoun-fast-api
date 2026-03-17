from __future__ import annotations

import re
import uuid
from contextvars import ContextVar

_REQUEST_ID_CTX: ContextVar[str | None] = ContextVar("request_id", default=None)

# Accept a conservative subset of common request-id formats:
# - UUID (with hyphens)
# - 16-64 chars of [A-Za-z0-9_-]
_SAFE_REQUEST_ID_RE = re.compile(r"^(?:[0-9a-fA-F-]{36}|[A-Za-z0-9_-]{16,64})$")


def get_request_id() -> str | None:
    """Return the current request correlation id (if set)."""
    return _REQUEST_ID_CTX.get()


def set_request_id(request_id: str | None) -> None:
    """Set the current request correlation id for this context."""
    _REQUEST_ID_CTX.set(request_id)


def new_request_id() -> str:
    """Create a new correlation id."""
    return str(uuid.uuid4())


def sanitize_incoming_request_id(value: str | None) -> str | None:
    """Validate an incoming request id header and return a safe value.

    Returns:
        A safe request id string or None if the provided value is missing/unsafe.
    """
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    if _SAFE_REQUEST_ID_RE.match(value):
        return value
    return None

