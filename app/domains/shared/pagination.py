"""Shared pagination helpers.

Provides the canonical pagination contract for all paginated list endpoints:

  External request params : page (1-based), pageSize, sortBy, sortOrder
  Internal Python names   : page, page_size, sort_by, sort_order, offset, limit
  Response fields         : items, total, page, pageSize, totalPages, hasNext, hasPrevious

Usage::

    from app.domains.shared.pagination import calculate_pagination, build_paginated_response

    meta = calculate_pagination(page=page, page_size=page_size, total=total_count)
    response = build_paginated_response(items=rows, meta=meta)
    return create_success_response(data=response, message=None)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Generic, List, Optional, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field, model_validator

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class PageParams(BaseModel):
    """Standard page + pageSize request parameters.

    Use as a dependency in routes that want typed injection::

        @router.get("")
        def list_items(params: Annotated[PageParams, Depends()]):
            meta = calculate_pagination(params.page, params.page_size, total)
    """

    page: int = Field(default=1, ge=1, description="1-based page index.")
    page_size: int = Field(
        default=20,
        ge=1,
        le=200,
        alias="pageSize",
        description="Number of items per page.",
    )

    model_config = {"populate_by_name": True}


class SortParams(BaseModel):
    """Standard sort request parameters with allow-list validation.

    Unknown ``sort_by`` values fall back to the default silently — no 400.
    ``sort_order`` is coerced to ``"asc"`` or ``"desc"``; anything else becomes ``"desc"``.
    """

    sort_by: str = Field(
        default="createdAt",
        alias="sortBy",
        description="Field to sort by (validated against endpoint allow-list).",
    )
    sort_order: str = Field(
        default="desc",
        alias="sortOrder",
        description="Sort direction: asc or desc.",
    )

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _normalize_sort_order(self) -> "SortParams":
        if self.sort_order.lower() not in ("asc", "desc"):
            self.sort_order = "desc"
        else:
            self.sort_order = self.sort_order.lower()
        return self


# ---------------------------------------------------------------------------
# Calculation result
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PaginationMeta:
    """Computed pagination metadata — single source of truth per request."""

    page: int
    page_size: int
    total: int
    offset: int
    total_pages: int
    has_next: bool
    has_previous: bool


def calculate_pagination(*, page: int, page_size: int, total: int) -> PaginationMeta:
    """Compute all pagination metadata from page / page_size / total.

    Args:
        page:       1-based page number (clamped to ≥ 1 defensively).
        page_size:  Items per page (clamped to ≥ 1 defensively).
        total:      Total matching rows in the collection.

    Returns:
        PaginationMeta with offset, total_pages, has_next, has_previous.
    """
    page = max(1, page)
    page_size = max(1, page_size)
    total = max(0, total)

    total_pages = math.ceil(total / page_size) if total > 0 else 0
    offset = (page - 1) * page_size

    return PaginationMeta(
        page=page,
        page_size=page_size,
        total=total,
        offset=offset,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_previous=page > 1,
    )


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard paginated response envelope.

    All paginated endpoints SHOULD use this (directly or by mirroring its fields)::

        class UserListResponse(PaginatedResponse[UserResponse]):
            pass
    """

    items: List[T]
    total: int
    page: int
    pageSize: int
    totalPages: int
    hasNext: bool
    hasPrevious: bool


def build_paginated_response(
    *,
    items: List[Any],
    meta: PaginationMeta,
    extra: Optional[dict] = None,
) -> dict:
    """Build a plain dict matching the paginated response envelope.

    Returns a dict rather than a typed model so it can be merged into existing
    domain response schemas without requiring full schema migration in one step.

    Args:
        items:  The page's data rows (already serialised or ORM objects).
        meta:   Computed ``PaginationMeta`` from ``calculate_pagination()``.
        extra:  Optional extra keys merged into the output dict.

    Returns:
        Dict suitable for use as ``data`` inside ``create_success_response()``.
    """
    payload: dict = {
        "items": items,
        "total": meta.total,
        "page": meta.page,
        "pageSize": meta.page_size,
        "totalPages": meta.total_pages,
        "hasNext": meta.has_next,
        "hasPrevious": meta.has_previous,
    }
    if extra:
        payload.update(extra)
    return payload


# ---------------------------------------------------------------------------
# Sort helper
# ---------------------------------------------------------------------------


def resolve_sort_column(
    sort_by: str,
    allow_list: dict,
    default_column: Any,
) -> Any:
    """Return the SQLAlchemy column corresponding to *sort_by*, or *default_column*.

    *sort_by* is NEVER forwarded to SQL directly.

    Args:
        sort_by:        The raw sort_by string from the request.
        allow_list:     Mapping of allowed sort_by strings → SQLAlchemy column/expression.
        default_column: Column to use when sort_by is not in allow_list.

    Returns:
        SQLAlchemy column (or expression) to use in order_by.

    Example::

        col = resolve_sort_column(
            sort_by=sort_by,
            allow_list={
                "createdAt": User.created_at,
                "fullName": User.full_name,
            },
            default_column=User.created_at,
        )
        stmt = stmt.order_by(col.desc() if sort_order == "desc" else col.asc())
    """
    return allow_list.get(sort_by, default_column)


# ---------------------------------------------------------------------------
# Legacy compat shim — kept for gradual migration
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Page:
    """Legacy Page dataclass; kept for backward compatibility with existing usages.

    New code should use :class:`PageParams` + :func:`calculate_pagination`.
    """

    page: int = 1
    page_size: int = 20
