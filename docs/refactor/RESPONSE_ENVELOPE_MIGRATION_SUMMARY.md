# Response envelope migration — summary

## Completed

- **Policy and inventory** — `RESPONSE_ENVELOPE_POLICY.md`, `RESPONSE_ENVELOPE_ENDPOINT_INVENTORY.md`, `RESPONSE_ENVELOPE_FE_IMPACT_LOG.md`.
- **Shared helpers** — `app/domains/shared/responses.py` (`pagination_public`, `merge_meta`); `app/utils/responses.py` updated to `StandardResponse` with `success`, `message`, `data`, `error`, `meta`; `create_success_response(..., pagination=...)` adds `meta.pagination`.
- **Unit tests** — `tests/unit/shared/test_response_envelope.py`; existing response utils tests updated for `ErrorResponse`.
- **Routes** — All v1 JSON handlers that previously returned raw models or partial wrappers now return the full success envelope where applicable; paginated and list endpoints set `meta.pagination` while **keeping** existing fields inside `data`.
- **Taxonomy** — Legacy `locations` / `property_taxonomy` and refactored `domains/taxonomy/router.py` aligned.
- **Properties & search** — List, exclusive, similar, detail, geo-search, and CSV import return the envelope; property search payload remains nested under `data`.
- **Error plan doc** — `RESPONSE_ENVELOPE_ERROR_PLAN.md` (HTTPException migration deferred).

## Not changed

- Route paths, methods, auth dependencies, and database schema.
- `GET /health` and metrics endpoints (non-envelope).
- Default FastAPI `HTTPException` body shape (see error plan).

## Validation

Run:

```bash
python -c "from app.main import app"
pytest tests/unit/shared/test_response_envelope.py -q
pytest tests/smoke/ -q
pytest tests/refactor_parity/ -q
```

## Frontend

See `RESPONSE_ENVELOPE_FE_IMPACT_LOG.md` for unwrap rules and high-impact endpoints (properties, taxonomy, geo-search).
