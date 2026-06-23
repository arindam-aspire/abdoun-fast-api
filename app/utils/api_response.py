from __future__ import annotations

from typing import Any


def success_response(data: Any = None, message: str | None = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "success": True,
        "message": message,
        "data": data,
        "error": None,
        "meta": meta or {},
    }
