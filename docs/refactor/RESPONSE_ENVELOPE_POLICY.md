# Response envelope policy

This document defines the canonical API success and error JSON shapes for `api/v1`. It applies to new and migrated handlers unless an endpoint is explicitly exempt (e.g. infrastructure routes).

## Rules

- Do not change route paths, HTTP methods, authentication, or database schema when adopting the envelope.
- Do not remove existing business fields from inner `data` payloads; additive fields (`meta`, top-level `error` on success) are allowed.
- Success responses use `create_success_response` from `app.utils.responses` (or equivalent) so `success`, `message`, `data`, `error`, and `meta` stay consistent.
- Paginated list endpoints also set `meta.pagination` (see below) while retaining any existing pagination fields inside `data` where they already exist.
- Validation and auth failures may still be returned as FastAPI `HTTPException` bodies (`{"detail": ...}`) until the global error handler migration (see `RESPONSE_ENVELOPE_ERROR_PLAN.md`).

## Success envelope

```json
{
  "success": true,
  "message": null,
  "data": {},
  "error": null,
  "meta": {}
}
```

- `message`: human-readable optional string on success (e.g. after mutations).
- `data`: domain payload (schemas unchanged unless a dedicated migration says otherwise).
- `error`: always `null` on success.
- `meta`: object; use `{}` when there is no extra metadata. Pagination uses `meta.pagination`.

Field order in JSON matches the Pydantic model field order in `StandardResponse`.

## Paginated success (`meta.pagination`)

For page-based lists, `meta` includes:

```json
{
  "pagination": {
    "total": 0,
    "page": 1,
    "pageSize": 20,
    "totalPages": 0,
    "hasNext": false,
    "hasPrevious": false
  }
}
```

Computed via `calculate_pagination` and passed to `create_success_response(..., pagination=meta)`. Inner `data` may still contain `items`, `users`, `agents`, nested `pagination`, etc., for backward compatibility.

## Error envelope (application-level)

For programmatic error objects built with `create_error_response`:

```json
{
  "success": false,
  "message": "Human-readable message",
  "data": null,
  "error": {
    "code": "ERROR_CODE",
    "details": {}
  },
  "meta": {}
}
```

HTTP status codes for these responses are chosen by the caller when returning a `JSONResponse`; many routes still raise `HTTPException` instead.

## Exemptions

- `GET /health` and metrics scrape endpoints are not wrapped.
- File downloads or raw streaming responses are out of scope unless they already return JSON.

## Implementation reference

- Helpers: `app/domains/shared/responses.py`, `app/utils/responses.py`
- Pagination: `app/domains/shared/pagination.py`
