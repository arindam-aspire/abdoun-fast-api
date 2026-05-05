# Error response envelope — follow-up plan

## Current state (after success-envelope migration)

- Success responses use `StandardResponse` via `create_success_response` with optional `meta.pagination`.
- Programmatic errors can be built with `create_error_response`, producing the documented `{ success: false, message, data: null, error: { code, details }, meta }` shape when returned as JSON.
- Most validation, auth, and not-found paths still use FastAPI `HTTPException`, which by default serializes as `{"detail": ...}` (string or list). This is **unchanged** to avoid a big-bang client migration.

## Recommended phases

1. **Document HTTP status mapping** — Maintain a table from HTTP status / internal exception type to `error.code` (e.g. `VALIDATION_ERROR`, `UNAUTHORIZED`, `NOT_FOUND`).
2. **Central exception handler** — Register `app.exception_handler(HTTPException)` (and optionally `RequestValidationError`) to translate into the standard error envelope while preserving the same status codes. Keep `detail` content inside `error.details` for debugging.
3. **Strangler pattern** — Optionally return the new envelope only for selected prefixes or `Accept`/header opt-in until the frontend switches globally.
4. **Logging and observability** — Log `error.code` and correlation id; avoid leaking sensitive data in `message`.

## Out of scope for this release

- Changing Cognito or third-party error payloads.
- Replacing `RateLimitExceeded` handler behavior without product sign-off.

## References

- Policy: `RESPONSE_ENVELOPE_POLICY.md`
- Helpers: `app/utils/responses.py` (`create_error_response`, `ErrorResponse`)
