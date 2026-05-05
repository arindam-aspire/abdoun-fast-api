# Frontend impact log — response envelope migration

Every consumer must unwrap responses with the common envelope:

- `response.success` — boolean
- `response.message` — optional string
- `response.data` — business payload (previous “root” for many endpoints)
- `response.error` — `null` on success
- `response.meta` — object; may contain `pagination` for list endpoints

## Breaking / structural

| Endpoint | Before (conceptual) | After |
|----------|---------------------|--------|
| GET `/properties`, `/properties/exclusive` | Root: `items`, `total`, `page`, `pageSize` | Same fields under `response.data` (inner payload is `PropertySearchResponse`) |
| GET `/properties/{id}` | Root: property detail object | Detail under `response.data` |
| GET `/properties/{id}/similar` | Root: search shape | Under `response.data`; `response.meta.pagination` added |
| POST `/properties/geo-search` | Root: `items`, `total` | Under `response.data`; `response.meta.pagination` added |
| POST `/properties/import-csv` | Root: `created`, … | Under `response.data` |
| GET `/location-taxonomy`, GET `/property-taxonomy` | Root: `{ data, total }` | That object is now `response.data`; envelope at root |
| All `StandardResponse` endpoints | Root: `success`, `data`, `message`, optional `error` (string) | Root adds `meta`; `error` is `null` or structured object for programmatic errors; success `error` is `null` |

## Additive (safe if FE ignores unknown keys)

| Change | Detail |
|--------|--------|
| `meta` | Usually `{}`; list endpoints include `meta.pagination` |
| `meta.pagination` | Mirrors totals/pages even when `data` already contains pagination fields |

## Needs FE verification

- Mobile / web clients that typed “raw” responses for properties or taxonomy without `StandardResponse`.
- Any client parsing pagination only from nested `data.pagination` should confirm `meta.pagination` if adopting the new standard.
- CSV import UI expecting top-level `created` only.

## Non-changes

- Paths, methods, auth headers, and query param names are unchanged.
- Health check `GET /health` remains unwrapped.
