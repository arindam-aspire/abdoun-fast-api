# Frontend Pagination Cleanup Checklist

> Backend has removed all old compat aliases. This file tells you exactly what to delete or rename in the frontend project.

---

## 1 — Query params to remove / rename

Search your codebase for every API call to these endpoints and apply the changes below.

### `GET /api/v1/agents`

| Remove / Change | Replace with |
|---|---|
| `?limit=N` | `?pageSize=N` |
| `?sort_by=X` | `?sortBy=X` |
| `?order=asc` / `?order=desc` | `?sortOrder=asc` / `?sortOrder=desc` |

### `GET /api/v1/agent-properties`
### `GET /api/v1/agent-properties/drafts`

| Remove / Change | Replace with |
|---|---|
| `?limit=N` | `?pageSize=N` |

### `GET /api/v1/admin/property-submissions`
### `GET /api/v1/admin/property-submissions/drafts`

| Remove / Change | Replace with |
|---|---|
| `?limit=N` | `?pageSize=N` |

### `GET /api/v1/admin/property-performance`

| Remove / Change | Replace with |
|---|---|
| `?limit=weekly` / `?limit=monthly` / `?limit=all` | `?period=weekly` / `?period=monthly` / `?period=all` |

---

## 2 — Response fields to remove from destructuring

For every place you read from these responses, delete the old fields and use the new ones.

### Agents response — `pagination` sub-object

```ts
// DELETE these reads:
pagination.limit        // removed
pagination.totalItems   // removed

// USE these instead:
pagination.pageSize     // same numeric value as limit was
pagination.total        // same numeric value as totalItems was
pagination.totalPages   // already existed
pagination.hasNext      // new
pagination.hasPrevious  // new
```

### Agent property-performance response — `pagination` sub-object

Same as agents above — remove `pagination.limit` and `pagination.totalItems`.

### Admin property-performance response — `pagination` sub-object

Same — remove `pagination.limit` and `pagination.totalItems`.

### `GET /api/v1/agent-properties`
### `GET /api/v1/agent-properties/drafts`

```ts
// DELETE:
response.limit          // removed from response

// USE:
response.pageSize       // same value
response.totalPages     // new
response.hasNext        // new
response.hasPrevious    // new
```

### `GET /api/v1/admin/property-submissions`

```ts
// DELETE:
response.limit          // removed from response

// USE:
response.pageSize       // same value
response.totalPages     // new
response.hasNext        // new
response.hasPrevious    // new
```

### `GET /api/v1/admin/property-submissions/drafts`

Same as admin submissions above.

---

## 3 — Anywhere you calculated totalPages yourself — delete the calculation

If you have something like this anywhere:

```ts
const totalPages = Math.ceil(total / pageSize);
const totalPages = Math.ceil(total / limit);
```

**Delete it.** The backend now returns `totalPages` directly on every paginated response.

---

## 4 — TypeScript types to update

Update your shared response types to match the new backend shapes exactly.

### `PaginationInfo` (used in agents, property-performance)

```ts
// BEFORE:
interface PaginationInfo {
  page:       number;
  limit:      number;    // ← delete
  totalItems: number;    // ← delete
  totalPages: number;
}

// AFTER:
interface PaginationInfo {
  page:         number;
  pageSize:     number;  // ← was limit
  total:        number;  // ← was totalItems
  totalPages:   number;
  hasNext:      boolean;
  hasPrevious:  boolean;
}
```

### `AgentPropertyListResponse`

```ts
// BEFORE:
interface AgentPropertyListResponse {
  items:    AgentPropertyListItem[];
  total:    number;
  page:     number;
  limit:    number;    // ← delete
}

// AFTER:
interface AgentPropertyListResponse {
  items:        AgentPropertyListItem[];
  total:        number;
  page:         number;
  pageSize:     number;
  totalPages:   number;
  hasNext:      boolean;
  hasPrevious:  boolean;
  draft_submissions?:       AgentDraftSubmissionItem[];
  draft_submissions_total?: number;
}
```

### `AgentDraftSubmissionListResponse`

```ts
// BEFORE:
interface AgentDraftSubmissionListResponse {
  items:  AgentDraftSubmissionItem[];
  total:  number;
  page:   number;
  limit:  number;    // ← delete
}

// AFTER:
interface AgentDraftSubmissionListResponse {
  items:        AgentDraftSubmissionItem[];
  total:        number;
  page:         number;
  pageSize:     number;
  totalPages:   number;
  hasNext:      boolean;
  hasPrevious:  boolean;
}
```

### `AdminSubmissionListResponse`

```ts
// BEFORE:
interface AdminSubmissionListResponse {
  items:  AdminSubmissionListItem[];
  page:   number;
  limit:  number;    // ← delete
  total:  number;
}

// AFTER:
interface AdminSubmissionListResponse {
  items:        AdminSubmissionListItem[];
  page:         number;
  total:        number;
  pageSize:     number;
  totalPages:   number;
  hasNext:      boolean;
  hasPrevious:  boolean;
}
```

### `UsersListResponse` — additive only (no deletes needed)

```ts
// ADD these fields (they were not there before):
interface UsersListResponse {
  users:        UserResponse[];
  total:        number;
  page:         number;
  pageSize:     number;
  totalPages:   number;   // ← new
  hasNext:      boolean;  // ← new
  hasPrevious:  boolean;  // ← new
}
```

---

## 5 — Endpoints deferred (no change yet — coordinate with backend)

These endpoints have **not changed** on the backend. Do not touch them yet.

| Endpoint | Reason deferred | Pending decision |
|---|---|---|
| `GET /api/v1/properties` | Response uses `data` not `items` | Agree on `data` → `items` rename or alias approach |
| `GET /api/v1/properties/exclusive` | Same as above | Same |
| `GET /api/v1/saved-searches` | Returns raw array, not `{items,total}` | Agree on wrapper format |
| `GET /api/v1/owners` | Uses `limit` + `offset` params | Confirm if endpoint is used on FE |

---

## 6 — Search terms to grep in the frontend project

Run these searches across your frontend codebase to find every place that needs updating:

```
grep -r "\.limit"                # reads of .limit response field
grep -r "limit="                 # ?limit= query params
grep -r "sort_by="               # old snake_case sort param
grep -r "\"order\""              # old order sort param
grep -r "totalItems"             # old totalItems field
grep -r "Math.ceil.*total"       # manual totalPages calculation
grep -r "Math.ceil.*pageSize"    # same
grep -r "Math.ceil.*limit"       # same with limit
```
