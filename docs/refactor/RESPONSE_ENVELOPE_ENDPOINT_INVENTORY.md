# Response envelope endpoint inventory

All listed routes are under the configured v1 prefix (typically `/api/v1`). Status reflects envelope migration: outer `{ success, message, data, error, meta }` with `meta.pagination` where noted.

## Group 1 — Low risk (taxonomy, uploads, owners CRUD)

| Method | Path | Notes |
|--------|------|--------|
| GET | `/location-taxonomy` | Wrapped; inner `data` still `{ data, total }` from service |
| GET | `/property-taxonomy` | Same |
| POST | `/uploads/...` | Wrapped (see OpenAPI for exact path) |
| GET/POST/PATCH/DELETE | `/owners` and sub-paths | Wrapped |

## Group 2 — Medium risk (lists, dashboards, agent property lists)

| Method | Path | `meta.pagination` |
|--------|------|-------------------|
| GET | `/users` | Yes |
| GET | `/agents` | Yes (list) |
| GET | `/admin/property-performance` | Yes |
| GET | `/agent/property-performance` | Yes |
| GET | `/agent-properties` | Yes |
| GET | `/agent-properties/drafts` | Yes |
| GET | `/admin/property-submissions` | Yes |
| GET | `/admin/property-submissions/drafts` | Yes |
| GET | `/favorites` | Yes (single-page semantic: page 1, `pageSize` ≥ total) |
| GET | `/users/recent-views` | Yes (same single-page semantic) |

## Group 3 — Authenticated CRUD (standard wrapper already; envelope extended)

| Area | Paths |
|------|--------|
| Saved searches | `/saved-searches` |
| Property submissions (user) | `/property-submissions` |
| Admin submissions | `/admin/property-submissions` |
| Recent views mutations | `POST/DELETE .../recent-views` |
| Favorites mutations | `POST/DELETE .../favorites` |
| Users admin | `/users/...` (non-list) |
| Agents admin | `/agents/...` (non-list) |
| Admin dashboard | `/admin/dashboard/...`, `/admin/recent-activity` |
| Admin properties | `/admin/properties/.../assign-agent` |
| Auth | `/auth/...` (handlers returning `StandardResponse` via service) |

## Group 4 — High risk (property search & geo)

| Method | Path | Notes |
|--------|------|--------|
| GET | `/properties` | Wrapped; inner payload remains `PropertySearchResponse` |
| GET | `/properties/exclusive` | Same |
| GET | `/properties/{id}/similar` | Wrapped + `meta.pagination` |
| GET | `/properties/{id}` | Wrapped; detail in `data` |
| POST | `/properties/geo-search` | Wrapped + `meta.pagination` (page 1, `pageSize` = request limit) |
| POST | `/properties/import-csv` | Wrapped; `data` = `ImportResponse` |

## Group 5 — Auth

| Notes |
|--------|
| All `AuthService` flows that return `create_success_response` inherit the envelope automatically. |
| Endpoints that only raise `HTTPException` are unchanged at the body level. |

## Feature flags

Domain routers re-export the same `app.api.v1.routes.*` modules for refactored flags, so inventory is identical for legacy and refactored wiring.

## Deferred / Needs FE verification

- Clients that assumed top-level property search fields (`data`, `total`, `page`, `pageSize`) must read them under `response.data` after migration.
- Geo search clients must read `items` / `total` under `response.data`.
- Taxonomy clients must read the prior root `{ data, total }` under `response.data`.
