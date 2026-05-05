# Pagination Policy

## Purpose

Define a single canonical pagination contract for all list endpoints in the Abdoun FastAPI codebase, reduce client confusion from divergent parameter names, and provide a shared implementation module that all routes can use.

---

## Request Format (External API)

All paginated endpoints MUST accept these query parameters:

| Parameter | Type | Default | Max | Notes |
|---|---|---|---|---|
| `page` | int ≥ 1 | 1 | — | 1-based page index |
| `pageSize` | int ≥ 1 | 20 | endpoint-specific | Items per page; each endpoint declares its own max |
| `sortBy` | string | endpoint-specific | — | Validated against allow-list per endpoint |
| `sortOrder` | string | `desc` | — | `asc` or `desc` only |

---

## Internal (Python) Format

Inside services and repositories always use snake_case:

```python
page: int            # 1-based
page_size: int       # items per page
sort_by: str         # allow-listed column name
sort_order: str      # "asc" or "desc"
offset: int          # (page - 1) * page_size  — computed by helper
limit: int           # alias for page_size at query layer
```

---

## Response Format

All paginated endpoints MUST return this envelope (wrapped in `StandardResponse.data` when the route uses the standard envelope):

```json
{
  "items": [],
  "total": 125,
  "page": 1,
  "pageSize": 20,
  "totalPages": 7,
  "hasNext": true,
  "hasPrevious": false
}
```

Field definitions:

| Field | Type | Description |
|---|---|---|
| `items` | list | The page's data rows |
| `total` | int | Total matching rows (across all pages) |
| `page` | int | Current page (1-based) |
| `pageSize` | int | Requested page size |
| `totalPages` | int | `ceil(total / pageSize)` |
| `hasNext` | bool | `page < totalPages` |
| `hasPrevious` | bool | `page > 1` |

**Endpoints that already have a nested pagination sub-object** (e.g. `agents`, `admin property-performance`) keep their existing `pagination: {…}` shape and add the new fields to it — do not flatten in the same release.

---

## Sorting Rules

1. `sortBy` is NEVER passed directly to SQL. It is validated against an explicit allow-list per endpoint.
2. Unknown `sortBy` values fall back to the endpoint's default sort column — no 400 error.
3. Sort allow-lists live in the route or service layer, not in the repository.
4. `sortOrder` accepts only `"asc"` or `"desc"` (case-insensitive). Any other value is coerced to `"desc"`.
5. Multi-column tie-breaking sorts are defined at the repository layer and not exposed as parameters.

---

## Backward Compatibility Rules

1. **Existing `limit` query params** that have already been released remain accepted as compat aliases. They are mapped to `page_size` internally. Do NOT remove them until the deprecation deadline.
2. **Existing `limit` response fields** stay present alongside `pageSize` until the compat window closes. Clients SHOULD migrate to `pageSize`.
3. **Existing `totalItems` fields** in nested pagination sub-objects remain present alongside `total`.
4. **`offset` query params** (owners endpoint) remain accepted but are undocumented in new clients; internally they still compute a page from the offset for the meta calculation.
5. Feature-flag-gated alternate domain routers are governed by the same policy once activated.

---

## Deprecation Rules

1. A deprecated alias MUST appear with `deprecated=True` in its `Query()` declaration.
2. Deprecation notice must be added to the endpoint docstring and to `PAGINATION_ENDPOINT_INVENTORY.md`.
3. Deprecated aliases may be removed only after a one-sprint (≥ 2 week) notice window to frontend teams.
4. Removal is tracked in the `PAGINATION_ENDPOINT_INVENTORY.md` `Decision` column.

---

## Examples

### Standard request

```
GET /api/v1/users?page=2&pageSize=50&sortBy=createdAt&sortOrder=asc
```

### Standard response (wrapped in StandardResponse)

```json
{
  "success": true,
  "data": {
    "items": [ /* ...user objects... */ ],
    "total": 120,
    "page": 2,
    "pageSize": 50,
    "totalPages": 3,
    "hasNext": true,
    "hasPrevious": true
  },
  "message": null
}
```

### Compat request (old clients)

```
GET /api/v1/agent-properties?page=1&limit=20
```

Both `limit` and `pageSize` are accepted; `pageSize` takes precedence when both are present.

---

## Using the Shared Helper

```python
from app.domains.shared.pagination import calculate_pagination, build_paginated_response

meta = calculate_pagination(page=page, page_size=page_size, total=total)
# meta.offset, meta.total_pages, meta.has_next, meta.has_previous

response_data = build_paginated_response(items=items, meta=meta)
return create_success_response(data=response_data, message=None)
```

---

## Endpoints Not Subject to This Policy

- Endpoints that intentionally return the full collection for an authenticated user (favorites list, saved searches list, recent views list). These return `{items, total}` without `page/pageSize`. They are documented in the inventory with `Decision = "full-list, no pagination"`.
- Internal scheduler/import endpoints with no external pagination contract.
