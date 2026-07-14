from __future__ import annotations

from typing import Any

from fastapi import HTTPException


def success_response(data: Any = None, message: str | None = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "success": True,
        "message": message,
        "data": data,
        "error": None,
        "meta": meta or {},
    }


def error_payload(*, code: str, message: str, details: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        payload["details"] = details
    return payload


def raise_api_error(
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
) -> None:
    raise HTTPException(
        status_code=status_code,
        detail=error_payload(code=code, message=message, details=details),
    )
