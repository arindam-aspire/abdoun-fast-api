# Pagination Frontend Impact Report

## Summary

This release implements the canonical pagination standard (see `PAGINATION_POLICY.md`). All changes are **additive only** — no existing fields have been renamed or removed. New fields are added to existing response bodies.

---

## Endpoints Changed in This Release

### `GET /api/v1/users` ✅ Additive only

| Field | Before | After |
|---|---|---|
| `users` | ✓ | ✓ |
| `total` | ✓ | ✓ |
| `page` | ✓ | ✓ |
| `pageSize` | ✓ | ✓ |
| `totalPages` | ✗ | ✓ (new) |
| `hasNext` | ✗ | ✓ (new) |
| `hasPrevious` | ✗ | ✓ (new) |

**Frontend action required:** None — new fields are additive. Frontend can optionally use `totalPages`, `hasNext`, `hasPrevious` to drive pagination controls.

---

### `GET /api/v1/agents` ✅ Additive only (nested `pagination` object)

| Field | Before | After |
|---|---|---|
| `pagination.page` | ✓ | ✓ |
| `pagination.limit` | ✓ | ✓ (kept for compat) |
| `pagination.totalItems` | ✓ | ✓ (kept for compat) |
| `pagination.totalPages` | ✓ | ✓ |
| `pagination.pageSize` | ✗ | ✓ (new, same value as `limit`) |
| `pagination.hasNext` | ✗ | ✓ (new) |
| `pagination.hasPrevious` | ✗ | ✓ (new) |

**Query param change:** `limit` and `sort_by` (snake_case) and `order` are still accepted. `pageSize` and `sortBy`/`sortOrder` are preferred. No removal planned yet.

**Frontend action required:** None for existing logic. Frontend may migrate to `pageSize` at its own pace.

---

### `GET /api/v1/admin/property-performance` ✅ Additive only

Same structure as agents: `pagination` sub-object gains `pageSize`, `hasNext`, `hasPrevious`. Existing `limit`/`totalItems` kept.

**Frontend action required:** None.

---

### `GET /api/v1/agent/property-performance` ✅ Additive only

Same as admin property-performance.

**Frontend action required:** None.

---

### `GET /api/v1/agent-properties` ⚠️ New `pageSize` param + additive response fields

**Query param change:**
- `pageSize` (canonical) is now accepted in addition to `limit` (deprecated).
- `limit` is still accepted for backward compat.
- When both are sent, `limit` takes precedence (legacy client safety).

**Response change (additive):**

| Field | Before | After |
|---|---|---|
| `items` | ✓ | ✓ |
| `total` | ✓ | ✓ |
| `page` | ✓ | ✓ |
| `limit` | ✓ | ✓ (kept for compat) |
| `pageSize` | ✗ | ✓ (new, same value as `limit`) |
| `totalPages` | ✗ | ✓ (new) |
| `hasNext` | ✗ | ✓ (new) |
| `hasPrevious` | ✗ | ✓ (new) |

**Frontend action required:** Migrate from `limit` to `pageSize` query param (no rush — `limit` still works). Can use new response fields for pagination UI.

**Deprecation deadline:** `limit` query param deprecated as of this release. Removal planned after ≥ 2 weeks of notice.

---

### `GET /api/v1/agent-properties/drafts` ⚠️ Same as above

Same additive changes as `/agent-properties`.

---

### `GET /api/v1/admin/property-submissions` ⚠️ New `pageSize` param + additive response fields

**Query param change:** `pageSize` now accepted; `limit` deprecated.

**Response change (additive):** Same new fields as agent-properties: `pageSize`, `totalPages`, `hasNext`, `hasPrevious`.

**Frontend action required:** Migrate from `limit` to `pageSize` over time.

---

### `GET /api/v1/admin/property-submissions/drafts` ⚠️ Same as admin submissions

---

## Endpoints NOT Changed in This Release (Deferred)

### `GET /api/v1/properties` — High Risk / Deferred

Current response uses `data` (not `items`) as the list field. Adding standard fields would need frontend alignment first.

**Pending fields to add:** `totalPages`, `hasNext`, `hasPrevious`.

**Blocker:** Frontend uses `data` key; would need coordinated rename or addition of `items` alias.

**Action:** Schedule with frontend team before next release.

---

### `GET /api/v1/properties/exclusive` — High Risk / Deferred

Same as `/api/v1/properties`.

---

### `POST /api/v1/properties/geo-search` — Deferred (non-paginated by design)

Map-based search returns all matching properties for a geographic bounding box. Not a page-based endpoint. No changes planned.

---

### `GET /api/v1/owners` — Pending (offset-based / low traffic)

Uses `limit` + `offset` parameters (no `page`). Needs migration to `page/pageSize` contract. Deferred until consumer impact is confirmed.

---

### `GET /api/v1/saved-searches` — Pending

Currently returns `List[SavedSearchResponse]` (raw list, no `{items, total}` wrapper). Wrapping in a standard envelope is a breaking change.

**Action:** Schedule with frontend team. Wrap in `{items, total}` in a future release.

---

## Backward Compatibility Guarantee

1. All deprecated query params (`limit` on `agent-properties`, `admin-submissions`) will continue to work until explicitly removed after a ≥ 2-week notice.
2. No existing response field has been renamed or removed.
3. All new response fields are additional; old client code ignores unknown fields by default.
4. The `PaginationInfo.limit` and `PaginationInfo.totalItems` fields in the agents/admin responses are preserved alongside the new standard fields.
