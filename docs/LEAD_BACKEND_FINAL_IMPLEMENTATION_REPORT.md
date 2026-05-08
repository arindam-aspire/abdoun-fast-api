# Lead Backend Final Implementation Report

Date: 2026-05-06
Scope: Lead Management backend only

## Progress By Checklist Item

### 1) Invalid transitions return HTTP 400

Status: Completed

Changes:
- Updated `LeadService.update_status` to catch workflow `ValueError` and return `HTTP 400` with business error detail.
- Added unit test to verify invalid transition now maps to `400`.

Files changed:
- `app/services/lead_service.py`
- `tests/unit/services/test_lead_service.py`

Validation:
- `pytest -q tests/unit/services/test_lead_service.py` -> passed (10 passed)

---

Further checklist items will be appended below as they are implemented and validated.

### 2) Add `GET /api/v1/leads/my`

Status: Completed

Changes:
- Added canonical registered-user list endpoint `GET /api/v1/leads/my`.
- Added `LeadService.list_my_leads(...)` with role enforcement (`registered_user` only).
- Added `LeadRepository.list_user_leads(...)`.
- Kept route thin; business logic remains in service/repository.

Files changed:
- `app/api/v1/routes/leads.py`
- `app/services/lead_service.py`
- `app/repositories/lead_repository.py`
- `tests/unit/api/routes/test_leads_routes.py`

Validation:
- `pytest -q tests/unit/services/test_lead_service.py tests/unit/api/routes/test_leads_routes.py` -> passed (16 passed)

### 3) Add `GET /api/v1/leads/{lead_id}`

Status: Completed

Changes:
- Added canonical shared lead-detail endpoint `GET /api/v1/leads/{lead_id}` (authenticated user, role checks in service/permission layer).
- Extended `LeadPermissionService` to support `registered_user` scope (`own lead only`).
- Added tests for registered-user own vs other-user lead access and shared route success.

Files changed:
- `app/api/v1/routes/leads.py`
- `app/services/lead_permission_service.py`
- `tests/unit/services/test_lead_permission_service.py`
- `tests/unit/api/routes/test_leads_routes.py`

Validation:
- `pytest -q tests/unit/services/test_lead_permission_service.py tests/unit/services/test_lead_service.py tests/unit/api/routes/test_leads_routes.py` -> passed (22 passed)

### 4) Add `GET/POST /api/v1/leads/{lead_id}/messages`

Status: Completed

Changes:
- Added canonical shared endpoints:
  - `GET /api/v1/leads/{lead_id}/messages`
  - `POST /api/v1/leads/{lead_id}/messages`
- Added `LeadService.list_messages(...)` and `LeadService.post_message(...)`.
- Kept compatibility wrapper `POST /api/v1/agent/leads/{lead_id}/reply`, now delegating to the same service logic (`post_message`).
- Added repository read method `list_messages`.

Files changed:
- `app/api/v1/routes/leads.py`
- `app/services/lead_service.py`
- `app/repositories/lead_repository.py`
- `app/schemas/lead.py`
- `tests/unit/api/routes/test_leads_routes.py`

Validation:
- `pytest -q tests/unit/services/test_lead_service.py tests/unit/api/routes/test_leads_routes.py` -> passed (20 passed)

### 5) Add notes APIs under `/api/v1/leads/{lead_id}/notes`

Status: Completed

Changes:
- Added canonical shared endpoints:
  - `GET /api/v1/leads/{lead_id}/notes`
  - `POST /api/v1/leads/{lead_id}/notes`
  - `PATCH /api/v1/leads/{lead_id}/notes/{note_id}`
  - `DELETE /api/v1/leads/{lead_id}/notes/{note_id}`
- Added `LeadService.list_notes(...)` and `LeadRepository.list_notes(...)`.
- Enforced rule: `registered_user` is forbidden for notes access and note mutation.
- Existing agent note endpoints remain as compatibility wrappers calling same service methods.

Files changed:
- `app/api/v1/routes/leads.py`
- `app/services/lead_service.py`
- `app/services/lead_permission_service.py`
- `app/repositories/lead_repository.py`
- `app/schemas/lead.py`
- `tests/unit/services/test_lead_permission_service.py`
- `tests/unit/services/test_lead_service.py`
- `tests/unit/api/routes/test_leads_routes.py`

Validation:
- `pytest -q tests/unit/services/test_lead_permission_service.py tests/unit/services/test_lead_service.py tests/unit/api/routes/test_leads_routes.py` -> passed (29 passed)

### 6) Add `GET /api/v1/leads/{lead_id}/history`

Status: Completed

Changes:
- Added canonical shared endpoint `GET /api/v1/leads/{lead_id}/history`.
- Added `LeadService.list_history(...)` and `LeadRepository.list_status_history(...)`.
- Enforced history access rule: `registered_user` forbidden; agent/admin routed through lead access checks.
- Added history response DTOs.

Files changed:
- `app/api/v1/routes/leads.py`
- `app/services/lead_service.py`
- `app/repositories/lead_repository.py`
- `app/schemas/lead.py`
- `tests/unit/services/test_lead_service.py`
- `tests/unit/api/routes/test_leads_routes.py`

Validation:
- `pytest -q tests/unit/services/test_lead_service.py tests/unit/api/routes/test_leads_routes.py` -> passed (25 passed)

### 7) Update admin lead access to full access

Status: Completed

Changes:
- Updated `LeadPermissionService` so admins have full lead access (no assignment-scope gate).
- Updated admin management scope check to role-only (`ensure_admin_can_manage_agent` now requires admin role, no scope mapping restriction).
- Updated admin lead listing to use full-access repository query (`list_admin_leads`) instead of scoped join.

Files changed:
- `app/services/lead_permission_service.py`
- `app/services/lead_service.py`
- `app/repositories/lead_repository.py`
- `tests/unit/services/test_lead_permission_service.py`
- `tests/unit/services/test_lead_service.py`

Validation:
- `pytest -q tests/unit/services/test_lead_permission_service.py tests/unit/services/test_lead_service.py tests/unit/api/routes/test_leads_routes.py` -> passed (32 passed)

### 8) Implement property unpublish on `CLOSED`

Status: Completed

Changes:
- Implemented close-time property unpublish in `LeadService.update_status(...)`.
- Added repository method `unpublish_property_on_lead_close(...)` that soft-unpublishes `properties_normalized` using existing fields:
  - `deleted_at`
  - `deleted_by`
  - `delete_reason`
- Unpublish now executes in the same transaction path as lead close/audit.

Files changed:
- `app/services/lead_service.py`
- `app/repositories/lead_repository.py`
- `tests/unit/services/test_lead_service.py`

Validation:
- `pytest -q tests/unit/services/test_lead_service.py` -> passed (13 passed)

### 9) Durable notifications integration (only if infrastructure exists)

Status: Deferred (no existing durable infrastructure found)

Assessment:
- `LeadNotificationService` is currently log-based (`emit_lead_event`, `emit_email_hook_todo`).
- No existing Lead notification persistence table/repository/service integration was found in-scope to wire durable in-app notifications without adding new cross-module infrastructure.

Decision:
- Kept current post-commit notification behavior.
- Marked durable notification integration as deferred to dedicated notification-infrastructure work.

Files changed:
- `docs/LEAD_BACKEND_FINAL_IMPLEMENTATION_REPORT.md` (documentation only)

Validation:
- N/A (no backend runtime code change in this item)

### 10) Update `docs/LEAD_API_CONTRACT.md`

Status: Completed

Changes:
- Added final canonical alignment section documenting:
  - canonical shared endpoints
  - retained list/status/close endpoints
  - compatibility wrappers
  - role-based service rules
  - workflow and status guarantees

Files changed:
- `docs/LEAD_API_CONTRACT.md`

Validation:
- `pytest -q tests/unit/api/routes/test_leads_routes.py` -> passed (13 passed)

### 11) Finalize implementation report

Status: Completed

## Final Canonical API Surface

Added/preferred shared canonical endpoints:
- `POST /api/v1/leads/contact-form`
- `GET /api/v1/leads/my`
- `GET /api/v1/leads/{lead_id}`
- `GET /api/v1/leads/{lead_id}/messages`
- `POST /api/v1/leads/{lead_id}/messages`
- `GET /api/v1/leads/{lead_id}/notes`
- `POST /api/v1/leads/{lead_id}/notes`
- `PATCH /api/v1/leads/{lead_id}/notes/{note_id}`
- `DELETE /api/v1/leads/{lead_id}/notes/{note_id}`
- `GET /api/v1/leads/{lead_id}/history`

Retained role-specific list/status endpoints:
- `GET /api/v1/agent/leads`
- `GET /api/v1/admin/leads`
- `PATCH /api/v1/agent/leads/{lead_id}/status`
- `PATCH /api/v1/admin/leads/{lead_id}/status`
- `POST /api/v1/admin/leads/{lead_id}/close-decision`

## Compatibility Wrappers Retained

- `GET /api/v1/agent/leads/{lead_id}` -> delegates to shared detail service logic.
- `POST /api/v1/agent/leads/{lead_id}/reply` -> delegates to shared message create service logic.
- Agent note endpoints under `/api/v1/agent/leads/{lead_id}/notes...` continue as wrapper-style compatibility routes using same service logic.

## APIs Removed/Deprecated

- No hard removals in this pass.
- Deprecated by contract guidance: role-split duplicates for shared resources/actions are superseded by canonical `/api/v1/leads/...` endpoints.

## Files Changed

- `alembic/versions/0040_add_lead_number_and_counters.py`
- `app/api/v1/routes/leads.py`
- `app/models/property_normalized.py`
- `app/repositories/lead_repository.py`
- `app/schemas/lead.py`
- `app/services/lead_permission_service.py`
- `app/services/lead_service.py`
- `docs/LEAD_API_CONTRACT.md`
- `docs/LEAD_BACKEND_FINAL_FIX_PLAN.md`
- `docs/LEAD_BACKEND_FINAL_IMPLEMENTATION_REPORT.md`
- `tests/unit/api/routes/test_leads_routes.py`
- `tests/unit/services/test_lead_permission_service.py`
- `tests/unit/services/test_lead_service.py`

## Migrations Added

- `0040_lead_display_identifiers` — `alembic/versions/0040_add_lead_number_and_counters.py`

## Tests Added/Updated

Updated tests cover:
- invalid transition -> `400`
- registered user own lead access vs forbidden other-user lead access
- shared messages routes + wrapper delegation
- shared notes routes + registered-user notes forbidden
- shared history route + registered-user history forbidden
- admin full access behavior
- close unpublishes property on `CLOSED`
- `leadNumber` assigned on contact-form and admin manual create; distinct allocation across successive creates
- list/detail include `leadNumber` and nested `property` summary where applicable

## Validation Results

Required final validation commands:
- `pytest -q tests/unit/services/test_lead_workflow_manager.py` -> passed (3 passed)
- `pytest -q tests/unit/services/test_lead_permission_service.py` -> passed (6 passed)
- `pytest -q tests/unit/services/test_lead_service.py` -> passed (16 passed)
- `pytest -q tests/unit/api/routes/test_leads_routes.py` -> passed (14 passed)

## Known Limitations

- Durable in-app lead notifications are deferred: current `LeadNotificationService` remains log-based and no in-scope durable notification infrastructure was available to integrate without cross-module expansion.

## Scope Confirmation

- Only Lead Management backend modules and Lead docs/tests were touched.
- No frontend files were modified.
- No `CONNECTED` status introduced; statuses remain exactly:
  - `NEW`
  - `IN_PROGRESS`
  - `REQUEST_FOR_CLOSE`
  - `CLOSED`

---

## Lead display identifiers & property snapshot (2026-05-06)

### Behavior

- **`id` (UUID)** remains the internal primary key and is used for all `{lead_id}` path parameters.
- **`leadNumber`** is the human-readable reference string `LD-YYYY-NNNNNN`, unique per lead, generated atomically (PostgreSQL `lead_number_counters` + `INSERT ... ON CONFLICT DO UPDATE RETURNING`).
- **`property`** on each `LeadItemResponse` adds `{ id, title, slug?, propertyHash?, thumbnailUrl? }` for UI display; **`propertyId`** is unchanged. **`propertyHash`** mirrors `properties_normalized.property_hash` so the frontend can link to property detail using the public numeric id (e.g. `/property-details/{propertyHash}`) instead of UUID. **`thumbnailUrl`** is a single preview image URL only; full image/media arrays are not included in Lead payloads.

### Migration

- **`0040_lead_display_identifiers`** (`alembic/versions/0040_add_lead_number_and_counters.py`): creates `lead_number_counters`, adds nullable `leads.lead_number`, backfills existing leads ordered by `created_at`, seeds counters per year, sets `NOT NULL`, unique index on `lead_number`.

### Files touched (this increment)

- `alembic/versions/0040_add_lead_number_and_counters.py`
- `app/models/property_normalized.py` (`Lead.lead_number`)
- `app/repositories/lead_repository.py` (`allocate_next_lead_number`, `get_property_summaries_by_ids`)
- `app/schemas/lead.py` (`PropertySummaryResponse`, `LeadItemResponse.leadNumber`, `LeadItemResponse.property`)
- `app/services/lead_service.py` (assign number on create; enrich list/detail payloads)
- `docs/LEAD_API_CONTRACT.md`
- `docs/LEAD_BACKEND_FINAL_IMPLEMENTATION_REPORT.md`
- `tests/unit/services/test_lead_service.py`
- `tests/unit/api/routes/test_leads_routes.py`

### Validation (post-change)

- `pytest -q tests/unit/services/test_lead_workflow_manager.py` — 3 passed
- `pytest -q tests/unit/services/test_lead_permission_service.py` — 6 passed
- `pytest -q tests/unit/services/test_lead_service.py` — 26 passed
- `pytest -q tests/unit/api/routes/test_leads_routes.py` — 14 passed

### Property public id in lead snapshot (follow-up)

- **`PropertySummaryResponse.propertyHash`** added; populated from `PropertyNormalized.property_hash` in `get_property_summaries_by_ids` for list and detail responses.
- **`PropertySummaryResponse.thumbnailUrl`** added; populated from normalized property media primary image thumbnail when available, with legacy first image fallback, and `null` when unavailable.

### Assigned agent display summary (follow-up)

- **`assignedAgentId`** remains unchanged as the assigned agent user UUID.
- **`assignedAgent`** was added as a display-only summary `{ id, fullName, email, phone }`, populated from existing `users.full_name`, `users.email`, and `users.phone_number`.
- Lead list responses fetch assigned agent summaries in one repository call per page (`get_agent_summaries_by_ids`) to avoid N+1 queries.

### Submitted user display summary and reassignment audit (follow-up)

- **`userId`** remains unchanged as the submitted/contact user UUID.
- **`user`** was added as a display-only summary `{ id, fullName, email, phone }`, populated from existing `users.full_name`, `users.email`, and `users.phone_number`.
- Lead list responses fetch submitted user summaries in one repository call per page (`get_user_summaries_by_ids`) to avoid N+1 queries.
- Admin reassignment now records a lead history row with unchanged status (`fromStatus == toStatus == current status`) and a clear reason: `Reassigned agent from {oldAgentId} to {newAgentId}`.
- Close history remains a status transition row (for example, `REQUEST_FOR_CLOSE -> CLOSED`) with `actorRole: admin` and the provided reason.

---

## Manual owner/external communication lead flow (2026-05-08)

### Behavior

- Added canonical endpoint `POST /api/v1/leads/manual` for agents to create manual owner leads.
- Manual owner leads use `source = AGENT_MANUAL`, `communicationMode = EXTERNAL`, `status = NEW`, `assignedAgentId = current agent`, `userId = null`, and `propertyId = null`.
- External owner details are stored on the lead row and serialized as `externalOwner`; related property display text is serialized as `externalPropertyName`.
- Existing contact-form inquiry flow remains unchanged and continues to use `communicationMode = IN_APP`.
- `GET /api/v1/leads/{lead_id}/messages` returns an empty list for `EXTERNAL` leads.
- `POST /api/v1/leads/{lead_id}/messages` returns `400` with `This lead uses external communication.` for `EXTERNAL` leads.
- Manual owner lead creation records history with reason `Manual owner lead created`; later status transitions, close, and reassignment continue through existing LeadService/audit paths.

### Migration

- **`0041_manual_owner_leads`** (`alembic/versions/0041_add_manual_owner_lead_fields.py`): adds `AGENT_MANUAL` to `lead_source_enum` and adds nullable external owner/property fields plus `communication_mode` (`NOT NULL DEFAULT 'IN_APP'`) and `created_by_agent_id`.

### Files touched (this increment)

- `alembic/versions/0041_add_manual_owner_lead_fields.py`
- `app/api/v1/routes/leads.py`
- `app/models/property_normalized.py`
- `app/schemas/lead.py`
- `app/services/lead_service.py`
- `docs/LEAD_API_CONTRACT.md`
- `docs/LEAD_BACKEND_FINAL_IMPLEMENTATION_REPORT.md`
- `tests/unit/services/test_lead_service.py`
- `tests/unit/api/routes/test_leads_routes.py`

### Validation (post-change)

- `pytest -q tests/unit/services/test_lead_service.py` — 33 passed
- `pytest -q tests/unit/api/routes/test_leads_routes.py` — 16 passed
- `pytest -q tests/unit/services/test_lead_permission_service.py` — 6 passed
