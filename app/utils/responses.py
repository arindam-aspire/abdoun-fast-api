"""Standard API response models and helpers: StandardResponse, ErrorResponse, PaginatedResponse, ImportResponse, create_*."""

from __future__ import annotations

from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

from app.domains.shared.pagination import PaginationMeta
from app.domains.shared.responses import merge_meta, pagination_public

T = TypeVar("T")


class ApiErrorBody(BaseModel):
    """Structured error payload inside the standard envelope."""

    code: str
    details: dict[str, Any] = Field(default_factory=dict)


class StandardResponse(BaseModel, Generic[T]):
    """Standard API success envelope."""

    success: bool = True
    message: Optional[str] = None
    data: Optional[T] = None
    error: Optional[ApiErrorBody] = None
    meta: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Standard API error envelope (for programmatic JSON errors)."""

    success: bool = False
    message: str
    data: None = None
    error: ApiErrorBody
    meta: dict[str, Any] = Field(default_factory=dict)


class PaginatedResponse(BaseModel, Generic[T]):
    """Legacy flat paginated payload (items + fields); prefer domain pagination helpers for new code."""

    items: List[T]
    total: int
    limit: Optional[int] = None
    offset: Optional[int] = None


class ImportResponse(BaseModel):
    """Response format for CSV import operations."""

    created: int
    updated: Optional[int] = None
    skipped: Optional[int] = None


def create_error_response(
    error: str,
    detail: Optional[str] = None,
    status_code: Optional[int] = None,
) -> ErrorResponse:
    """Build a standardized error envelope."""
    details: dict[str, Any] = {}
    if detail is not None:
        details["detail"] = detail
    code = f"HTTP_{status_code}" if status_code is not None else "ERROR"
    return ErrorResponse(
        message=error,
        error=ApiErrorBody(code=code, details=details),
    )


def create_success_response(
    data: Any,
    message: Optional[str] = None,
    meta: Optional[dict[str, Any]] = None,
    *,
    pagination: Optional[PaginationMeta] = None,
) -> StandardResponse[Any]:
    """Build a standardized success StandardResponse.

    Args:
        data: Domain payload.
        message: Optional human-readable message.
        meta: Optional extra metadata merged into ``meta``.
        pagination: When set, adds ``meta.pagination`` from shared pagination rules.
    """
    merged = merge_meta(meta, {"pagination": pagination_public(pagination)} if pagination else None)
    return StandardResponse(
        success=True,
        message=message,
        data=data,
        error=None,
        meta=merged,
    )
