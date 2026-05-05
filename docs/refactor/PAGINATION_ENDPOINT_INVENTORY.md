# Pagination Endpoint Inventory

All paginated and list endpoints. `Decision` column documents the migration status and any pending action.

## Group A — Low Risk (Implemented)

| Endpoint | File | Request Params (before) | Request Params (after) | Response (before) | Response (after) | Sorting | Risk | Decision |
|---|---|---|---|---|---|---|---|---|
| `GET /api/v1/users` | `routes/users.py` | `page`, `pageSize` (alias) | same + no change | `{users, total, page, pageSize}` | adds `totalPages, hasNext, hasPrevious` | none | Low | ✅ Implemented — additive fields only |
| `GET /api/v1/agents` | `routes/agents.py` | `page`, `pageSize` (alias), `limit` compat, `sort_by`/`sortBy` compat | same (no change) | nested `pagination {page, limit, totalItems, totalPages}` | adds `pageSize, hasNext, hasPrevious` | allow-listed: `invitedAt`, `fullName`, `email` | Low | ✅ Implemented — additive fields only; `limit` compat retained |
| `GET /api/v1/admin/property-performance` | `routes/admin.py` | `page`, `pageSize` (alias), `limit` compat for period | same (no change) | nested `pagination {page, limit, totalItems, totalPages}` | adds `pageSize, hasNext, hasPrevious` | none (sorted by view count) | Low | ✅ Implemented — inline `math.ceil` replaced by helper |
| `GET /api/v1/agent/property-performance` | `routes/agent.py` | `page`, `pageSize` (alias), `limit` for period | same (no change) | same nested shape | adds `pageSize, hasNext, hasPrevious` | none | Low | ✅ Implemented |
| `GET /api/v1/agent-properties` | `routes/agent_properties.py` | `page`, `limit` | adds `pageSize` alias for `limit` | `{items, total, page, limit}` | adds `pageSize, totalPages, hasNext, hasPrevious` | none | Low | ✅ Implemented — `limit` retained as compat |
| `GET /api/v1/agent-properties/drafts` | `routes/agent_properties.py` | `page`, `limit` | adds `pageSize` alias for `limit` | `{items, total, page, limit}` | adds `pageSize, totalPages, hasNext, hasPrevious` | none | Low | ✅ Implemented |
| `GET /api/v1/admin/property-submissions` | `routes/admin_property_submissions.py` | `page`, `limit` | adds `pageSize` alias for `limit` | `{items, page, limit, total}` | adds `pageSize, totalPages, hasNext, hasPrevious` | none | Low | ✅ Implemented |
| `GET /api/v1/admin/property-submissions/drafts` | `routes/admin_property_submissions.py` | `page`, `limit` | adds `pageSize` alias for `limit` | `{items, total, page, limit}` | adds `pageSize, totalPages, hasNext, hasPrevious` | none | Low | ✅ Implemented |

## Group B — Full-List Endpoints (No Pagination Added)

These endpoints intentionally return the full collection for the current user. They are documented here but not subject to `page/pageSize` pagination.

| Endpoint | File | Response Shape | Decision |
|---|---|---|---|
| `GET /api/v1/favorites` | `routes/favorites.py` | `{items, total}` | ✅ Full-list — no pagination needed |
| `GET /api/v1/saved-searches` | `routes/saved_searches.py` | `List[SavedSearchResponse]` — raw list | ⚠️ Inconsistent — missing `{items, total}` wrapper. Tracked separately |
| `GET /api/v1/users/recent-views` | `routes/recent_views.py` | `{items, total}` (max 10) | ✅ Full-list — no pagination needed |

### Saved searches inconsistency note
`GET /api/v1/saved-searches` returns a raw `List[SavedSearchResponse]` with no metadata wrapper. This is inconsistent with all other list endpoints. Recommendation: wrap in `{items, total}` in a future release (coordinate with frontend).

## Group C — High Risk (Properties / Geo-search)

These endpoints have deep frontend contracts. No structural response changes in this release. They are documented for awareness.

| Endpoint | File | Params | Current Response | Contract Owner | Decision |
|---|---|---|---|---|---|
| `GET /api/v1/properties` | `routes/properties.py` | `page`, `pageSize` (alias) | `{items, total, page, pageSize}` inside envelope `data` | Frontend search UI | `meta.pagination` on envelope; inner list key is `items` |
| `GET /api/v1/properties/exclusive` | `routes/properties.py` | same | same | Frontend search UI | 🟡 Defer |
| `GET /api/v1/properties/{id}/similar` | `routes/properties.py` | `limit` only | `{items, total, page=1, pageSize=len}` inside envelope | Frontend | non-paginated similar endpoint |
| `POST /api/v1/properties/geo-search` | `routes/search.py` | `limit` in body | `{items, total}` — no page metadata | Map UI | 🟡 Defer — geo-search is not page-based by design |

## Owner Endpoint (Offset-based — Pending)

| Endpoint | File | Params | Decision |
|---|---|---|---|
| `GET /api/v1/owners` | `routes/owners.py` | `limit`, `offset` | ⚠️ Pending — needs migration to `page/pageSize` but low traffic endpoint; coordinate with consumer before change |

## Deprecated Aliases

| Endpoint | Alias | Standard Name | Deprecated Since | Removal Target |
|---|---|---|---|---|
| `GET /api/v1/agent-properties` | `limit` query param | `pageSize` | This release | TBD (≥ 2 weeks notice to frontend) |
| `GET /api/v1/agent-properties/drafts` | `limit` query param | `pageSize` | This release | TBD |
| `GET /api/v1/admin/property-submissions` | `limit` query param | `pageSize` | This release | TBD |
| `GET /api/v1/admin/property-submissions/drafts` | `limit` query param | `pageSize` | This release | TBD |
| `GET /api/v1/agents` | `limit` query compat | `pageSize` | Previously existing | TBD |
| `GET /api/v1/agents` | `sort_by` query compat | `sortBy` | Previously existing | TBD |
| `GET /api/v1/agents` | `order` query compat | `sortOrder` | Previously existing | TBD |
