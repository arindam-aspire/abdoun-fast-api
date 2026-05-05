"""Response envelope helpers for API handlers.

Canonical shapes are documented in ``docs/refactor/RESPONSE_ENVELOPE_POLICY.md``.
"""

from __future__ import annotations

from typing import Any

from app.domains.shared.pagination import PaginationMeta


def pagination_public(meta: PaginationMeta) -> dict[str, Any]:
    """Build the ``meta.pagination`` object (camelCase keys, public contract)."""
    return {
        "total": meta.total,
        "page": meta.page,
        "pageSize": meta.page_size,
        "totalPages": meta.total_pages,
        "hasNext": meta.has_next,
        "hasPrevious": meta.has_previous,
    }


def merge_meta(*parts: dict[str, Any] | None) -> dict[str, Any]:
    """Merge meta dicts; later keys overwrite earlier ones."""
    out: dict[str, Any] = {}
    for p in parts:
        if p:
            out.update(p)
    return out


def as_payload(data: Any) -> dict[str, Any]:
    """Legacy helper: single-key wrapper (prefer ``create_success_response``)."""
    return {"data": data}
