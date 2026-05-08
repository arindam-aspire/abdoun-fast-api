# Lead Management API Contract

## 1. Overview

These APIs support lead handling for three actor types:
- **Registered user**: submits contact-form inquiry from property UI.
- **Agent**: views and manages assigned leads (status, replies, notes).
- **Admin**: manages all leads (manual creation, reassign, status/close decision).

Flow summary:
- **Contact-form flow**: `POST /api/v1/leads/contact-form` creates lead with `NEW` + `EMAIL_FORM`.
- **Agent workflow**: list/detail + progress to `IN_PROGRESS`, then request close.
- **Admin workflow**: list all leads, manual create (`PHONE`/`WHATSAPP`/`MANUAL_ADMIN`), reassign, status updates, close decision.
- **Manual owner flow**: `POST /api/v1/leads/manual` lets an agent create an external-communication lead with `NEW` + `AGENT_MANUAL`.
- **Status lifecycle** is controlled by workflow policy and enforced in service layer.

---

## 2. Authentication & Roles

- Auth mechanism: Bearer token via `Authorization: Bearer <token>`.
- Route guards use `require_role(...)` dependency.
- Roles used by lead routes:
  - `registered_user`
  - `agent`
  - `admin`

Scope limitations:
- **Registered user**: contact-form create action and own-lead read/message access.
- **Agent**: can access only leads where `assigned_agent_id == current_user.id`.
- **Admin**: full access to Lead Management resources unless a route has a narrower business operation.

---

## 3. Status Lifecycle

Allowed statuses:

```text
NEW
IN_PROGRESS
REQUEST_FOR_CLOSE
CLOSED
```

Allowed transitions:

```text
NEW -> IN_PROGRESS
IN_PROGRESS -> REQUEST_FOR_CLOSE
REQUEST_FOR_CLOSE -> CLOSED
```

Rules:
- `CLOSED` is terminal.
- Agent transitions: `NEW -> IN_PROGRESS`, `IN_PROGRESS -> REQUEST_FOR_CLOSE`.
- Admin can perform scoped transitions and is required for `... -> CLOSED`.
- Service enforces additional guard: non-admin cannot set `CLOSED`.

---

## 4. Shared Models / DTOs

Source: `app/schemas/lead.py`

### ContactFormLeadCreateRequest

| Field | Type | Required | Validation | Notes |
|---|---|---|---|---|
| `propertyId` | string / UUID | Yes | Non-empty | Property: UUID string, or numeric `property_hash` (e.g. from listing URL) resolved server-side to internal UUID |
| `name` | string | Yes | min 2, max 20 | Currently validated but not persisted to lead row |
| `email` | string | Yes | min 5, max 255 | Format is frontend/business-validated; schema has length constraints |
| `phoneNumber` | string | Yes | min 8, max 20 | Country-code-aware formatting expected by frontend |
| `message` | string | Yes | min 10, max 1000 | Stored in lead row |

### AdminManualLeadCreateRequest

| Field | Type | Required | Validation | Notes |
|---|---|---|---|---|
| `propertyId` | UUID | Yes | UUID | Lead property |
| `assignedAgentId` | UUID | Yes | UUID | Must be admin-scoped |
| `source` | string | Yes | `^(PHONE|WHATSAPP|MANUAL_ADMIN)$` | Manual/admin channel |
| `message` | string | Yes | min 10, max 1000 | Lead message |
| `contactUserId` | UUID \| null | No | UUID if provided | Optional user link |

### ManualOwnerLeadCreateRequest

| Field | Type | Required | Validation | Notes |
|---|---|---|---|---|
| `ownerName` | string | Yes | min 1, max 255 | External property owner name |
| `phoneNumber` | string \| null | Conditional | min 7, max 50 if present | At least one of `phoneNumber` or `email` is required |
| `email` | email string \| null | Conditional | Email format if present | At least one of `phoneNumber` or `email` is required |
| `message` | string | Yes | min 1, max 1000 | Stored on `leads.message` |
| `relatedPropertyName` | string | Yes | min 1, max 255 | Stored as external display property name |

### LeadStatusUpdateRequest

| Field | Type | Required | Validation | Notes |
|---|---|---|---|---|
| `status` | string | Yes | `^(NEW|IN_PROGRESS|REQUEST_FOR_CLOSE|CLOSED)$` | Must also satisfy transition matrix |
| `reason` | string \| null | No | max 500 | Stored in status history |

### LeadReassignRequest

| Field | Type | Required | Validation | Notes |
|---|---|---|---|---|
| `assignedAgentId` | UUID | Yes | UUID | New scoped agent |

### LeadReplyRequest

| Field | Type | Required | Validation | Notes |
|---|---|---|---|---|
| `message` | string | Yes | min 1, max 1000 | Creates `lead_messages` row |

### LeadNoteCreateRequest / LeadNoteUpdateRequest

| Field | Type | Required | Validation | Notes |
|---|---|---|---|---|
| `note` | string | Yes | min 1, max 2000 | Internal note |

### LeadItemResponse

| Field | Type | Required | Validation | Notes |
|---|---|---|---|---|
| `id` | UUID | Yes | UUID | Primary key for APIs and joins (internal id). |
| `leadNumber` | string | Yes | Unique display reference `LD-YYYY-NNNNNN` | Human-readable lead reference; use for UI labels (not for URL path params — paths remain UUID `{lead_id}`). |
| `propertyId` | UUID \| null | No | UUID if present | Unchanged; FK to property. |
| `property` | object \| null | No | See below | Display-only snapshot for lists/detail (title via default/en convention); omit or null if property missing. |
| `userId` | UUID \| null | No | UUID if present | Requesting user |
| `user` | object \| null | No | See below | Display-only submitted/contact user summary for UI |
| `communicationMode` | string \| null | No | `IN_APP` or `EXTERNAL` | Existing inquiry leads use `IN_APP`; manual owner leads use `EXTERNAL`. |
| `externalOwner` | object \| null | No | See below | External owner display summary for manual owner leads. |
| `externalPropertyName` | string \| null | No | | Related external property display name for manual owner leads. |
| `createdByAgentId` | UUID \| null | No | UUID if present | Agent who created an external/manual owner lead. |
| `status` | string | Yes | lifecycle values | |
| `source` | string | Yes | source values | |
| `assignedAgentId` | UUID \| null | No | UUID if present | Unchanged agent FK/id |
| `assignedAgent` | object \| null | No | See below | Display-only agent summary for lead tables/detail |
| `assignedByAdminId` | UUID \| null | No | UUID if present | |
| `message` | string \| null | No | | |
| `lastActivityAt` | datetime \| null | No | ISO timestamp | |
| `requestCloseAt` | datetime \| null | No | ISO timestamp | |
| `closedAt` | datetime \| null | No | ISO timestamp | |
| `closedByAdminId` | UUID \| null | No | UUID if present | |
| `createdAt` | datetime | Yes | ISO timestamp | |
| `updatedAt` | datetime | Yes | ISO timestamp | |

### PropertySummaryResponse (nested under `property`)

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | Yes | Property UUID string |
| `title` | string \| null | No | Resolved via `get_title_description_for_language` default/en fallback |
| `slug` | string \| null | No | Optional slug derived from title for linking |
| `thumbnailUrl` | string \| null | No | Single thumbnail URL for lead previews; normalized media primary image thumb first, legacy first image fallback |
| `propertyHash` | int \| null | No | `properties_normalized.property_hash` — public numeric id for routes such as `/property-details/{propertyHash}` and `GET /api/v1/properties/{property_id}` |

### AssignedAgentSummaryResponse (nested under `assignedAgent`)

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | Yes | Agent user UUID string |
| `fullName` | string \| null | No | From `users.full_name` |
| `email` | string \| null | No | From `users.email` |
| `phone` | string \| null | No | From `users.phone_number` |

### LeadUserSummaryResponse (nested under `user`)

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | Yes | Submitted/contact user UUID string |
| `fullName` | string \| null | No | From `users.full_name` |
| `email` | string \| null | No | From `users.email` |
| `phone` | string \| null | No | From `users.phone_number` |

### ExternalOwnerSummaryResponse (nested under `externalOwner`)

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string \| null | No | External owner name |
| `email` | string \| null | No | External owner email |
| `phone` | string \| null | No | External owner phone |

### LeadListResponse

| Field | Type | Required | Validation | Notes |
|---|---|---|---|---|
| `items` | LeadItemResponse[] | Yes | | |
| `total` | int | Yes | >= 0 | Total matching rows |
| `page` | int | Yes | >= 1 | Page index |
| `pageSize` | int | Yes | >= 1 | Page size |

### LeadNoteResponse

| Field | Type | Required | Validation | Notes |
|---|---|---|---|---|
| `id` | UUID | Yes | UUID | |
| `leadId` | UUID | Yes | UUID | |
| `authorUserId` | UUID \| null | No | UUID if present | |
| `note` | string | Yes | | |
| `createdAt` | datetime | Yes | ISO timestamp | |
| `updatedAt` | datetime | Yes | ISO timestamp | |

### LeadReplyResponse

| Field | Type | Required | Validation | Notes |
|---|---|---|---|---|
| `id` | UUID | Yes | UUID | Message ID |
| `leadId` | UUID | Yes | UUID | |
| `senderUserId` | UUID \| null | No | UUID if present | |
| `recipientUserId` | UUID \| null | No | UUID if present | |
| `message` | string | Yes | | |
| `channel` | string | Yes | currently `IN_APP` | |
| `deliveryState` | string \| null | No | | |
| `createdAt` | datetime | Yes | ISO timestamp | |

History DTO:
- Not exposed directly by current API contracts.

---

## 5. API Details

Response envelope (success):

```json
{
  "success": true,
  "data": {},
  "message": null,
  "error": null
}
```

Error envelope:
- For business/auth errors raised by `HTTPException`, FastAPI default shape applies:

```json
{
  "detail": "Error message"
}
```

- For validation (`422`) default FastAPI validation payload applies (`detail` array with field errors).

### POST /api/v1/leads/contact-form

**Purpose:** Create lead from registered-user contact form.  
**Auth:** Bearer token required.  
**Allowed Roles:** `registered_user`.  
**Path Params:** None.  
**Query Params:** None.  
**Request Body:** `ContactFormLeadCreateRequest`.  
**Success Response:** `StandardResponse<LeadItemResponse>`.  
**Error Responses:** `401`, `403`, `404` (property/agent mapping), `422`, `500`.  
**Frontend Notes:** Backend currently persists `message` and assignment metadata; `name/email/phoneNumber` are validated in request but not stored in lead table.

Example request:

```json
{
  "propertyId": "00000000-0000-0000-0000-000000000001",
  "name": "John Doe",
  "email": "john@example.com",
  "phoneNumber": "+12025551234",
  "message": "I am interested in this property."
}
```

Example success:

```json
{
  "success": true,
  "data": {
    "id": "11111111-1111-1111-1111-111111111111",
    "propertyId": "00000000-0000-0000-0000-000000000001",
    "userId": "22222222-2222-2222-2222-222222222222",
    "status": "NEW",
    "source": "EMAIL_FORM",
    "assignedAgentId": "33333333-3333-3333-3333-333333333333",
    "assignedByAdminId": null,
    "message": "I am interested in this property.",
    "lastActivityAt": "2026-05-05T14:00:00Z",
    "requestCloseAt": null,
    "closedAt": null,
    "closedByAdminId": null,
    "createdAt": "2026-05-05T14:00:00Z",
    "updatedAt": "2026-05-05T14:00:00Z"
  },
  "message": "Your inquiry has been sent successfully",
  "error": null
}
```

### POST /api/v1/leads/manual

**Purpose:** Agent creates a manual owner lead where owner communication happens outside the app.  
**Auth:** Bearer token required.  
**Allowed Roles:** `agent`.  
**Path Params:** None.  
**Query Params:** None.  
**Request Body:** `ManualOwnerLeadCreateRequest`.  
**Success Response:** `StandardResponse<LeadItemResponse>`.  
**Error Responses:** `401`, `403` (registered user/admin/non-agent), `422`, `500`.

Creation rules:
- `status = NEW`
- `source = AGENT_MANUAL`
- `communicationMode = EXTERNAL`
- `assignedAgentId = current agent id`
- `userId = null`
- `propertyId = null`
- creation is recorded in lead history with reason `Manual owner lead created`

Example request:

```json
{
  "ownerName": "Owner Name",
  "phoneNumber": "+962799999999",
  "email": "owner@example.com",
  "message": "Owner wants to sell or rent property",
  "relatedPropertyName": "Villa in Abdoun"
}
```

Example response data:

```json
{
  "leadNumber": "LD-2026-000014",
  "status": "NEW",
  "source": "AGENT_MANUAL",
  "communicationMode": "EXTERNAL",
  "externalOwner": {
    "name": "Owner Name",
    "email": "owner@example.com",
    "phone": "+962799999999"
  },
  "externalPropertyName": "Villa in Abdoun",
  "assignedAgentId": "33333333-3333-3333-3333-333333333333",
  "userId": null,
  "user": null,
  "propertyId": null,
  "property": null
}
```

### GET /api/v1/agent/leads

**Purpose:** Paginated lead list for authenticated agent.  
**Auth:** Bearer token required.  
**Allowed Roles:** `agent`.  
**Path Params:** None.  
**Query Params:** `status?`, `source?`, `page` (>=1), `pageSize` (1..100).  
**Request Body:** None.  
**Success Response:** `StandardResponse<LeadListResponse>`.  
**Error Responses:** `401`, `403`, `422`, `500`.  
**Frontend Notes:** Only assigned leads are returned.

### GET /api/v1/agent/leads/{lead_id}

**Purpose:** Lead detail for assigned agent.  
**Auth:** Bearer token required.  
**Allowed Roles:** `agent`.  
**Path Params:** `lead_id: UUID`.  
**Query Params:** None.  
**Request Body:** None.  
**Success Response:** `StandardResponse<LeadItemResponse>`.  
**Error Responses:** `401`, `403`, `404`, `422`, `500`.  
**Frontend Notes:** `403` when lead is outside agent scope.

### PATCH /api/v1/agent/leads/{lead_id}/status

**Purpose:** Agent updates status in allowed flow.  
**Auth:** Bearer token required.  
**Allowed Roles:** `agent`.  
**Path Params:** `lead_id: UUID`.  
**Query Params:** None.  
**Request Body:** `LeadStatusUpdateRequest`.  
**Success Response:** `StandardResponse<LeadItemResponse>`.  
**Error Responses:** `401`, `403`, `404`, `422`, `500`.  
**Frontend Notes:** Invalid transitions return `400`.

### POST /api/v1/agent/leads/{lead_id}/reply

**Purpose:** Send lead reply; stores message and emits notification hooks.  
**Auth:** Bearer token required.  
**Allowed Roles:** `agent`.  
**Path Params:** `lead_id: UUID`.  
**Query Params:** None.  
**Request Body:** `LeadReplyRequest`.  
**Success Response:** `StandardResponse<LeadReplyResponse>`.  
**Error Responses:** `401`, `403`, `404`, `422`, `500`.  
**Frontend Notes:** If lead status is `NEW`, backend auto-promotes to `IN_PROGRESS`.

### POST /api/v1/agent/leads/{lead_id}/notes

**Purpose:** Add internal note.  
**Auth:** Bearer token required.  
**Allowed Roles:** `agent`.  
**Path Params:** `lead_id: UUID`.  
**Query Params:** None.  
**Request Body:** `LeadNoteCreateRequest`.  
**Success Response:** `StandardResponse<LeadNoteResponse>`.  
**Error Responses:** `401`, `403`, `404`, `422`, `500`.  
**Frontend Notes:** Notes are internal only.

### PATCH /api/v1/agent/leads/{lead_id}/notes/{note_id}

**Purpose:** Update note (owner/admin scope rule enforced).  
**Auth:** Bearer token required.  
**Allowed Roles:** `agent`.  
**Path Params:** `lead_id`, `note_id` UUIDs.  
**Query Params:** None.  
**Request Body:** `LeadNoteUpdateRequest`.  
**Success Response:** `StandardResponse<LeadNoteResponse>`.  
**Error Responses:** `401`, `403`, `404`, `422`, `500`.  
**Frontend Notes:** Agent can edit only own notes.

### DELETE /api/v1/agent/leads/{lead_id}/notes/{note_id}

**Purpose:** Delete note (owner/admin scope rule enforced).  
**Auth:** Bearer token required.  
**Allowed Roles:** `agent`.  
**Path Params:** `lead_id`, `note_id` UUIDs.  
**Query Params:** None.  
**Request Body:** None.  
**Success Response:** `StandardResponse<bool>`.  
**Error Responses:** `401`, `403`, `404`, `422`, `500`.  
**Frontend Notes:** Returns `data: true` on success.

### GET /api/v1/admin/leads

**Purpose:** Paginated lead list for admin.  
**Auth:** Bearer token required.  
**Allowed Roles:** `admin`.  
**Path Params:** None.  
**Query Params:** `status?`, `source?`, `page` (>=1), `pageSize` (1..100).  
**Request Body:** None.  
**Success Response:** `StandardResponse<LeadListResponse>`.  
**Error Responses:** `401`, `403`, `422`, `500`.  
**Frontend Notes:** Admin has full lead-list access.

### POST /api/v1/admin/leads

**Purpose:** Create manual lead (e.g., phone/WhatsApp/manual admin source).  
**Auth:** Bearer token required.  
**Allowed Roles:** `admin`.  
**Path Params:** None.  
**Query Params:** None.  
**Request Body:** `AdminManualLeadCreateRequest`.  
**Success Response:** `StandardResponse<LeadItemResponse>`.  
**Error Responses:** `401`, `403`, `422`, `500`.  
**Frontend Notes:** `assignedAgentId` must belong to admin scope.

Example request:

```json
{
  "propertyId": "00000000-0000-0000-0000-000000000001",
  "assignedAgentId": "33333333-3333-3333-3333-333333333333",
  "source": "PHONE",
  "message": "Phone inquiry captured by admin",
  "contactUserId": null
}
```

### PATCH /api/v1/admin/leads/{lead_id}/reassign

**Purpose:** Reassign lead to another scoped agent.  
**Auth:** Bearer token required.  
**Allowed Roles:** `admin`.  
**Path Params:** `lead_id: UUID`.  
**Query Params:** None.  
**Request Body:** `LeadReassignRequest`.  
**Success Response:** `StandardResponse<LeadItemResponse>`.  
**Error Responses:** `401`, `403`, `404`, `422`, `500`.  
**Frontend Notes:** Both lead scope and target agent scope are validated.

### PATCH /api/v1/admin/leads/{lead_id}/status

**Purpose:** Admin status update for scoped lead.  
**Auth:** Bearer token required.  
**Allowed Roles:** `admin`.  
**Path Params:** `lead_id: UUID`.  
**Query Params:** None.  
**Request Body:** `LeadStatusUpdateRequest`.  
**Success Response:** `StandardResponse<LeadItemResponse>`.  
**Error Responses:** `401`, `403`, `404`, `422`, `500`.  
**Frontend Notes:** Use lifecycle rules; invalid transition handling same caveat as agent status endpoint.

### POST /api/v1/admin/leads/{lead_id}/close-decision

**Purpose:** Close decision action endpoint (currently shares `update_status` service path).  
**Auth:** Bearer token required.  
**Allowed Roles:** `admin`.  
**Path Params:** `lead_id: UUID`.  
**Query Params:** None.  
**Request Body:** `LeadStatusUpdateRequest`.  
**Success Response:** `StandardResponse<LeadItemResponse>`.  
**Error Responses:** `401`, `403`, `404`, `422`, `500`.  
**Frontend Notes:** Expected business use is close decision (`... -> CLOSED`); route technically accepts any allowed status payload. **Needs confirmation** whether frontend should lock to `CLOSED` only.

---

## 6. Contact Form Flow

Frontend flow:
1. User clicks contact option.
2. Validate fields client-side:
   - Name: 2-20 chars
   - Email: valid format + length constraints
   - Phone: country-code-aware project standard
   - Message: 10-1000 chars
3. Call `POST /api/v1/leads/contact-form`.
4. Backend creates `NEW` lead with `EMAIL_FORM` and assigned listing agent.
5. Backend dedupe: same property/user/message within short window returns existing lead instead of inserting duplicate.
6. Handle success message and errors.

---

## 7. Agent Lead Flow

- Fetch list: `GET /api/v1/agent/leads`
- Open detail: `GET /api/v1/agent/leads/{lead_id}`
- Update status: `PATCH /api/v1/agent/leads/{lead_id}/status`
- Reply: `POST /api/v1/agent/leads/{lead_id}/reply`
- Manage notes:
  - create `POST .../notes`
  - update `PATCH .../notes/{note_id}`
  - delete `DELETE .../notes/{note_id}`

Scope rule:
- Agent can access only assigned leads.

Allowed transitions for agent:
- `NEW -> IN_PROGRESS`
- `IN_PROGRESS -> REQUEST_FOR_CLOSE`

---

## 8. Admin Lead Flow

- List scoped leads: `GET /api/v1/admin/leads`
- Create manual lead: `POST /api/v1/admin/leads`
- Reassign lead: `PATCH /api/v1/admin/leads/{lead_id}/reassign`
- Update status: `PATCH /api/v1/admin/leads/{lead_id}/status`
- Close decision: `POST /api/v1/admin/leads/{lead_id}/close-decision`

Scope rule:
- Admin can access only leads tied to agents assigned to that admin.

Admin close rule:
- Admin can apply `REQUEST_FOR_CLOSE -> CLOSED`.

---

## 9. Error Handling Guide for Frontend

- `401 Unauthorized`
  - Missing/invalid token.
  - Action: prompt re-auth.

- `403 Forbidden`
  - Role mismatch or scope violation (e.g., agent accessing unassigned lead).
  - Action: show permission message; avoid retry loops.

- `404 Not Found`
  - Lead/note/property association not found.
  - Action: show not-found state and refresh list.

- `400 Invalid transition`
  - **Current implementation note:** invalid transition may bubble to `500` (needs explicit mapping in service if desired).
  - Action: treat unexpected status-change failures as non-retryable business error.

- `422 Validation Error`
  - Request payload constraint failure.
  - Action: bind field errors to form UI.

- Duplicate submission
  - Contact-form duplicate may return success with existing lead payload (idempotent behavior).
  - Action: treat as success and continue UX flow.

- `500 Internal Server Error`
  - DB or unhandled server error.
  - Action: show generic retry toast and capture telemetry.

---

## 10. Frontend Integration Checklist

- API client methods for all 12 lead endpoints.
- Query/mutation hooks for:
  - contact-form create
  - agent list/detail/status/reply/notes
  - admin list/create/reassign/status/close-decision
- UI pages/components:
  - property contact form
  - agent lead list/detail drawer/modal
  - admin lead management table + actions
- Frontend validation:
  - contact form, status forms, notes/reply lengths
- Status badge mapping:
  - `NEW`, `IN_PROGRESS`, `REQUEST_FOR_CLOSE`, `CLOSED`
- Action visibility:
  - agent vs admin based on role + current status
- Error toast strategy:
  - 401/403/404/422/500 handling
- Pagination/filter wiring:
  - `page`, `pageSize`, optional `status`, `source`
- Role-based UI gating:
  - registered user (contact and own leads)
  - agent (assigned leads only, manual owner create)
  - admin (full lead access)

---

## OpenAPI Verification

Documented endpoints were cross-checked against registered OpenAPI paths.

- Missing from OpenAPI: **none**
- Extra lead-management endpoints in OpenAPI but undocumented: **none**
- Note: `/api/v1/agents/leaderboard` contains lead analytics but is outside Lead Management API scope and intentionally excluded.

---

## Final Canonical Backend Alignment (2026-05-06)

This section supersedes older role-split guidance where action/resource is the same.

### Canonical shared endpoints (preferred)

- `POST /api/v1/leads/contact-form`
- `POST /api/v1/leads/manual`
- `GET /api/v1/leads/my`
- `GET /api/v1/leads/{lead_id}`
- `GET /api/v1/leads/{lead_id}/messages`
- `POST /api/v1/leads/{lead_id}/messages`
- `GET /api/v1/leads/{lead_id}/notes`
- `POST /api/v1/leads/{lead_id}/notes`
- `PATCH /api/v1/leads/{lead_id}/notes/{note_id}`
- `DELETE /api/v1/leads/{lead_id}/notes/{note_id}`
- `GET /api/v1/leads/{lead_id}/history`

### List/status/close endpoints retained

- `GET /api/v1/agent/leads` (retained list endpoint)
- `GET /api/v1/admin/leads` (retained list endpoint; admin full access)
- `PATCH /api/v1/agent/leads/{lead_id}/status` (retained)
- `PATCH /api/v1/admin/leads/{lead_id}/status` (retained)
- `POST /api/v1/admin/leads/{lead_id}/close-decision` (canonical close decision)

### Compatibility wrappers retained

- `GET /api/v1/agent/leads/{lead_id}` -> delegates to shared lead-detail service logic.
- `POST /api/v1/agent/leads/{lead_id}/reply` -> delegates to shared message-create service logic (`POST /api/v1/leads/{lead_id}/messages`).
- Agent note endpoints under `/api/v1/agent/leads/{lead_id}/notes...` remain functional wrappers to shared note service logic.

### Role rules (service-layer enforced)

- `registered_user`
  - Can list own leads (`/leads/my`)
  - Can view only own lead detail/messages
  - Can post messages only on own leads
  - Forbidden for notes and history

- `agent`
  - Access limited to assigned leads
  - Can create manual owner/external leads through `POST /api/v1/leads/manual`
  - Can read/post messages on assigned leads
  - Can manage notes on assigned leads; update/delete only own notes
  - Can view history for assigned leads

- `admin`
  - Full access to all leads
  - Can read all messages
  - Can view/add notes
  - Can view all history
  - `CLOSED` transition via close decision path; close action unpublishes property

### Status and workflow guarantees

- Allowed statuses only: `NEW`, `IN_PROGRESS`, `REQUEST_FOR_CLOSE`, `CLOSED`
- Allowed transitions: `NEW -> IN_PROGRESS -> REQUEST_FOR_CLOSE -> CLOSED`
- Invalid transition returns `HTTP 400`
- Permission failure returns `HTTP 403`
- `CONNECTED` status is not used

### Manual owner/external communication flow (2026-05-08)

- `POST /api/v1/leads/manual` is the canonical manual owner lead creation endpoint for agents.
- Manual owner leads are stored with `source = AGENT_MANUAL`, `communicationMode = EXTERNAL`, `status = NEW`, `assignedAgentId = current agent`, `userId = null`, and `propertyId = null`.
- External owner data is returned as `externalOwner`; the related property name is returned as `externalPropertyName`.
- Existing contact-form leads remain `IN_APP` and continue to use the in-app message thread.
- For `EXTERNAL` leads, `GET /api/v1/leads/{lead_id}/messages` returns an empty list and `POST /api/v1/leads/{lead_id}/messages` returns `400` with `This lead uses external communication.`
- Manual owner leads follow the same status lifecycle: `NEW -> IN_PROGRESS -> REQUEST_FOR_CLOSE -> CLOSED`.

### Lead display identifiers and property snapshot (2026-05-06)

- **`id` (UUID)** remains the canonical identifier for API routes (`/leads/{lead_id}`, etc.).
- **`leadNumber`** (`LD-YYYY-NNNNNN`) is assigned server-side, unique, safe under concurrency via table `lead_number_counters` and PostgreSQL upsert. Migration `0040_lead_display_identifiers` adds `leads.lead_number`, backfills existing rows, and enforces a unique index.
- **`property`** on list/detail items is a display snapshot `{ id, title, slug?, propertyHash?, thumbnailUrl? }`. **`propertyId`** is unchanged. Title follows existing translation helper default/en behavior (`get_title_description_for_language`); `slug` is a simple derived slug from title when present. **`propertyHash`** is `properties_normalized.property_hash` for frontend routes that expect the numeric public id (e.g. `/property-details/981376612`). **`thumbnailUrl`** is a single preview image URL, not an image/media array.
- **`assignedAgent`** is a display-only summary `{ id, fullName, email, phone }`; **`assignedAgentId`** remains unchanged.
- **`user`** is a display-only submitted/contact user summary `{ id, fullName, email, phone }`; **`userId`** remains unchanged.
- Lead reassignment history is represented in the existing history stream as an unchanged-status row with a reason describing old/new assigned agent ids.
