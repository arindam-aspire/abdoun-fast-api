# Frontend Pagination Migration Guide

> **For:** Frontend developers  
> **Backend release:** Pagination standardisation (Apr 2026)  
> **Breaking changes:** None — all existing params and fields still work  
> **New fields available immediately:** Yes

---

## TL;DR

The backend now returns extra pagination fields on every paginated endpoint.
**Nothing breaks.** But you should:

1. **Stop sending `limit=` on agent-properties and admin-submissions** — use `pageSize=` instead (deprecation clock is running).
2. **Use the new `totalPages`, `hasNext`, `hasPrevious` fields** to drive pagination controls instead of calculating them yourself.
3. **Read the "Needs your input" section** — two endpoints need a joint decision before the backend can complete their migration.

---

## 1 — New standard response shape

Every paginated endpoint now returns (inside `data` when using StandardResponse):

```json
{
  "items":       [],
  "total":       125,
  "page":        2,
  "pageSize":    20,
  "totalPages":  7,
  "hasNext":     true,
  "hasPrevious": true
}
```

If your component was calculating `totalPages = Math.ceil(total / pageSize)` itself, you can now read it directly from the response.

---

## 2 — Endpoints: what changed, what to update

### ✅ Nothing to change right now (additive only)

These endpoints received new fields. Your existing code still works. Optionally adopt `hasNext`/`hasPrevious`/`totalPages` when convenient.

---

#### `GET /api/v1/users`

**Before (still works):**
```ts
const { users, total, page, pageSize } = response.data;
const totalPages = Math.ceil(total / pageSize); // you calculated this
```

**After (new fields available):**
```ts
const { users, total, page, pageSize, totalPages, hasNext, hasPrevious } = response.data;
// totalPages, hasNext, hasPrevious are ready to use — no calculation needed
```

Likely files to update: admin user list page / table component.

---

#### `GET /api/v1/agents`

Response shape is nested under a `pagination` object:

**Before (still works):**
```ts
const { agents, pagination } = response.data;
const { page, limit, totalItems, totalPages } = pagination;
```

**After (new fields on pagination object):**
```ts
const { agents, pagination } = response.data;
const {
  page,
  limit,        // still here — compat
  totalItems,   // still here — compat
  totalPages,   // was already here
  pageSize,     // NEW — same value as limit
  hasNext,      // NEW
  hasPrevious,  // NEW
} = pagination;
```

**Query param migration** (no rush, but prefer):
```
Before: GET /api/v1/agents?page=1&limit=20
After:  GET /api/v1/agents?page=1&pageSize=20
```

Likely files: admin agents table / management page.

---

#### `GET /api/v1/admin/property-performance`
#### `GET /api/v1/agent/property-performance`

Same nested `pagination` object as agents above. New fields: `pageSize`, `hasNext`, `hasPrevious`.

Likely files: admin/agent dashboard charts or property performance tables.

---

### ⚠️ Migrate query params — deadline pending

These endpoints have deprecated `limit=` and replaced it with `pageSize=`.  
`limit=` still works but **will be removed after a ≥ 2 week notice window**.

---

#### `GET /api/v1/agent-properties`
#### `GET /api/v1/agent-properties/drafts`

**Query param — migrate now:**
```
Before: GET /api/v1/agent-properties?page=1&limit=20
After:  GET /api/v1/agent-properties?page=1&pageSize=20
```

**Response — new fields added:**
```ts
// Before (still works)
const { items, total, page, limit } = response.data;

// After — all old fields still present, plus:
const { items, total, page, limit, pageSize, totalPages, hasNext, hasPrevious } = response.data;
```

Likely files: agent dashboard "My Listings" table, agent drafts list.

---

#### `GET /api/v1/admin/property-submissions`
#### `GET /api/v1/admin/property-submissions/drafts`

**Query param — migrate now:**
```
Before: GET /api/v1/admin/property-submissions?page=1&limit=10
After:  GET /api/v1/admin/property-submissions?page=1&pageSize=10
```

**Response — new fields added:**
```ts
// Before (still works)
const { items, page, limit, total } = response.data;

// After:
const { items, page, limit, total, pageSize, totalPages, hasNext, hasPrevious } = response.data;
```

Likely files: admin moderation queue / submission review table.

---

## 3 — Needs your input (joint decisions)

These endpoints are **blocked** on a decision from the frontend team before the backend can complete migration.

---

### `GET /api/v1/properties` and `GET /api/v1/properties/exclusive`

**Current backend response:**
```json
{
  "data":     [],
  "total":    125,
  "page":     2,
  "pageSize": 12
}
```

**Standard response would use `items` instead of `data`.**

The backend needs to know which of these two options the frontend can accept:

| Option | Response change | Impact |
|---|---|---|
| A — Add `items` alias alongside `data` | Both `data` and `items` present (compat) | Low — no existing code breaks |
| B — Rename `data` to `items` in a new version | Breaking for existing search UI | High — all search/listing pages must update |

**Action needed from frontend:** Confirm Option A or B, and agree on a release date.  
Until confirmed, these endpoints are **not changed**.

---

### `GET /api/v1/saved-searches`

**Current backend response:**
```json
[ { "id": "...", "name": "..." }, ... ]
```
(A raw array — no `{items, total}` wrapper.)

**Standard would be:**
```json
{
  "items": [ { "id": "...", "name": "..." }, ... ],
  "total": 5
}
```

This is a **breaking change** for any code that does `response.data.map(...)` or `response.data.length`.

**Action needed from frontend:** Confirm when this can be updated. Backend will wrap in `{items, total}` at the agreed time.

---

### `GET /api/v1/owners`

Currently uses `limit` + `offset` (no `page`). This is a low-traffic admin endpoint.

**Current:** `GET /api/v1/owners?limit=50&offset=0`  
**Standard would be:** `GET /api/v1/owners?page=1&pageSize=50`

**Action needed from frontend:** Confirm whether this endpoint is used and when migration is safe.

---

## 4 — TypeScript type updates (if you have a shared types file)

If you maintain response types, here are the updated shapes:

```ts
// Canonical paginated response (new standard)
interface PaginatedResponse<T> {
  items:       T[];
  total:       number;
  page:        number;
  pageSize:    number;
  totalPages:  number;
  hasNext:     boolean;
  hasPrevious: boolean;
}

// Nested pagination sub-object (agents, property-performance)
interface PaginationInfo {
  page:         number;
  limit:        number;   // deprecated — use pageSize
  totalItems:   number;   // deprecated — use total from parent
  totalPages:   number;
  pageSize:     number;   // new
  hasNext:      boolean;  // new
  hasPrevious:  boolean;  // new
}

// Users list (flat, not nested)
interface UsersListResponse extends PaginatedResponse<UserResponse> {
  users: UserResponse[];  // field is "users" not "items"
}
```

---

## 5 — Priority order

| Priority | Endpoint | Action | Deadline |
|---|---|---|---|
| 🔴 High | `GET /agent-properties` | Change `limit=` → `pageSize=` in query | Before deprecation removal |
| 🔴 High | `GET /agent-properties/drafts` | Same | Before deprecation removal |
| 🔴 High | `GET /admin/property-submissions` | Change `limit=` → `pageSize=` | Before deprecation removal |
| 🔴 High | `GET /admin/property-submissions/drafts` | Same | Before deprecation removal |
| 🟡 Medium | `GET /properties` | Agree on `data` vs `items` with backend | Joint decision required |
| 🟡 Medium | `GET /saved-searches` | Agree on wrapping raw list | Joint decision required |
| 🟢 Low | `GET /users` | Optionally adopt `totalPages`/`hasNext` | No deadline |
| 🟢 Low | `GET /agents` | Optionally adopt `pageSize` query param | No deadline |
| 🟢 Low | `GET /admin/property-performance` | Optionally use new pagination fields | No deadline |
| ⚪ Defer | `GET /owners` | Confirm usage first | TBD |

---

## 6 — Summary of deprecated query params

| Endpoint | Old param | New param | Works until |
|---|---|---|---|
| `GET /agent-properties` | `limit` | `pageSize` | ≥ 2 weeks from Apr 2026 |
| `GET /agent-properties/drafts` | `limit` | `pageSize` | ≥ 2 weeks from Apr 2026 |
| `GET /admin/property-submissions` | `limit` | `pageSize` | ≥ 2 weeks from Apr 2026 |
| `GET /admin/property-submissions/drafts` | `limit` | `pageSize` | ≥ 2 weeks from Apr 2026 |
| `GET /agents` | `limit` (compat) | `pageSize` | Existing compat — TBD |
| `GET /agents` | `sort_by` (snake_case) | `sortBy` | Existing compat — TBD |
| `GET /agents` | `order` | `sortOrder` | Existing compat — TBD |
