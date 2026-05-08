# Lead Management Audit Report (Backend)

Generated: 2026-05-06  
Scope: Backend Lead Management module (API + service + repository + persistence + audit trail)

## 1) Executive summary

The Lead Management backend is **implemented end-to-end** with:

- **Role-scoped APIs** for `registered_user`, `agent`, and `admin`.
- **Lifecycle workflow** enforced centrally with a strict transition matrix.
- **Persistence** via a dedicated repository and new lifecycle tables (`lead_status_history`, `lead_notes`, `lead_messages`).
- **Audit trail** for status transitions written on every successful transition.
- **Notification hooks** currently implemented as structured logs (TODO for durable delivery).
- **Unit tests** covering workflow, permissions, service orchestration, and route wiring.

The module is production-shaped for core workflows (create → work → request close → close), but has a few explicit “by design / TODO” items (notably notification delivery and mapping invalid transitions to 4xx instead of 5xx).

## 2) Current state (what exists today)

### 2.1 Features implemented

- **Lead creation**
  - Registered user contact-form lead creation (`EMAIL_FORM` source) with **dedupe**.
  - Admin manual lead creation with explicit sources (`PHONE`, `WHATSAPP`, `MANUAL_ADMIN`) and scoped assignment.
- **Lead viewing**
  - Agent list + detail for **assigned** leads.
  - Admin list for leads **scoped** to admin’s assigned agents.
- **Lead updates**
  - Status updates via workflow policy (`NEW → IN_PROGRESS → REQUEST_FOR_CLOSE → CLOSED`).
  - Admin lead reassignment to another scoped agent.
- **Lead collaboration artifacts**
  - Agent notes CRUD with ownership enforcement (agent can modify only own notes; admin can modify any scoped).
  - Agent reply message persistence; reply auto-promotes `NEW → IN_PROGRESS`.
- **Audit trail**
  - Status transition history persisted for creates and status transitions.

### 2.2 What is intentionally not implemented (known gaps / deferred scope)

- **Durable notifications**: `LeadNotificationService` logs events and “email TODO hooks” only.
- **Explicit API for history/notes/messages retrieval**: status history is written but not exposed as an endpoint contract.
- **Property state side-effects** on close: hook exists but is `TODO` (auto-unpublish controlled by `lead_auto_unpublish_on_close` setting, not wired).
- **Reopen / cancel / priority / tags / attachments / exports / bulk actions**: not included by scope.

## 3) Architecture & code ownership map

### 3.1 Entry points (API layer)

File: `app/api/v1/routes/leads.py`

- Public route(s):
  - `POST /api/v1/leads/contact-form`
- Agent route(s) (prefixed by `/api/v1/agent` in router composition):
  - `GET /api/v1/agent/leads`
  - `GET /api/v1/agent/leads/{lead_id}`
  - `PATCH /api/v1/agent/leads/{lead_id}/status`
  - `POST /api/v1/agent/leads/{lead_id}/reply`
  - `POST /api/v1/agent/leads/{lead_id}/notes`
  - `PATCH /api/v1/agent/leads/{lead_id}/notes/{note_id}`
  - `DELETE /api/v1/agent/leads/{lead_id}/notes/{note_id}`
- Admin route(s) (prefixed by `/api/v1/admin` in router composition):
  - `GET /api/v1/admin/leads`
  - `POST /api/v1/admin/leads`
  - `PATCH /api/v1/admin/leads/{lead_id}/reassign`
  - `PATCH /api/v1/admin/leads/{lead_id}/status`
  - `POST /api/v1/admin/leads/{lead_id}/close-decision`

### 3.2 Dependency wiring (DI)

File: `app/api/v1/deps/leads.py`

The dependency factory composes the module as:

- `LeadRepository(db)`
- `LeadWorkflowManager()`
- `LeadPermissionService(repo)`
- `LeadAuditService(repo)`
- `LeadNotificationService()`
- `LeadService(repo, workflow, permission, audit, notifications)`

This keeps API routes thin and consolidates business orchestration in a single service entry point.

### 3.3 Service split (policy vs orchestration)

- `LeadService` (`app/services/lead_service.py`)
  - Orchestrates use-cases and manages transactions (commit/rollback).
  - Calls into workflow/permission/audit/notification collaborators.
- `LeadWorkflowManager` (`app/services/lead_workflow_manager.py`)
  - Enforces allowed status transitions.
- `LeadPermissionService` (`app/services/lead_permission_service.py`)
  - Enforces scope rules (agent assignment and admin→agent assignment mapping) and note ownership.
- `LeadAuditService` (`app/services/lead_audit_service.py`)
  - Writes `lead_status_history` rows for transitions.
- `LeadNotificationService` (`app/services/lead_notification_service.py`)
  - Emits events via logs (placeholder for real dispatch).

### 3.4 Persistence layer (repository)

File: `app/repositories/lead_repository.py`

Responsibilities implemented:

- Query scoped lead lists for agent/admin.
- Create lead, notes, messages, and status history rows.
- Dedupe detection for contact form (`property_id`, `user_id`, `source=EMAIL_FORM`, same `message`, within a short time window).
- Scope lookup through `admin_agent_assignments` to enforce admin visibility and admin “manage agent” constraints.
- Explicit `commit()` and `rollback()` helpers.

## 4) Data model and database migration

### 4.1 ORM models

File: `app/models/property_normalized.py`

- `Lead`
  - Lifecycle columns: `status`, `source`, `assigned_agent_id`, `assigned_by_admin_id`, `last_activity_at`, `request_close_at`, `closed_at`, `closed_by_admin_id`
  - Primary content: `message`
- `LeadStatusHistory`
  - `lead_id`, `from_status`, `to_status`, `actor_user_id`, `actor_role`, `reason`, `changed_at`
- `LeadNote`
  - `lead_id`, `author_user_id`, `note`, `created_at`, `updated_at`
- `LeadMessage`
  - `lead_id`, `sender_user_id`, `recipient_user_id`, `message`, `channel`, `delivery_state`, `created_at`

### 4.2 Migration

File: `alembic/versions/0039_add_lead_lifecycle_tables.py`

Adds:

- Enum types:
  - `lead_status_enum`: `NEW`, `IN_PROGRESS`, `REQUEST_FOR_CLOSE`, `CLOSED`
  - `lead_source_enum`: `EMAIL_FORM`, `PHONE`, `WHATSAPP`, `MANUAL_ADMIN`
  - `lead_message_channel_enum`: `IN_APP`, `EMAIL`
- Lead lifecycle columns + FKs on the existing `leads` table
- New tables:
  - `lead_status_history`
  - `lead_notes`
  - `lead_messages`
- Indexes supporting:
  - agent lead inbox queries
  - status/source filtering
  - history timeline queries

## 5) Authentication, authorization, and scoping

### 5.1 Route-level enforcement

Lead routes use `require_role(...)` guards, matching:

- Contact-form: `registered_user`
- Agent routes: `agent`
- Admin routes: `admin`

### 5.2 Data-level scope enforcement

Enforced centrally in `LeadPermissionService`:

- **Agent** can access only leads where `lead.assigned_agent_id == actor.id`.
- **Admin** can access only leads where the lead’s `assigned_agent_id` is within the admin’s active scope via `admin_agent_assignments`:
  - `AdminAgentAssignment(admin_id=actor.id, agent_id=lead.assigned_agent_id, is_active=true)`

### 5.3 Note ownership enforcement

- Admin can modify any scoped note.
- Agent can modify only notes they authored (`note.author_user_id == actor.id`).

## 6) Lifecycle workflow (status state machine)

### 6.1 Allowed status values

- `NEW`
- `IN_PROGRESS`
- `REQUEST_FOR_CLOSE`
- `CLOSED` (terminal)

### 6.2 Allowed transitions

Enforced by `LeadWorkflowManager`:

- `NEW → IN_PROGRESS`
- `IN_PROGRESS → REQUEST_FOR_CLOSE`
- `REQUEST_FOR_CLOSE → CLOSED`
- `CLOSED → (no transitions)`

### 6.3 Additional role constraints

Enforced in `LeadService.update_status`:

- Only **admin** may set `CLOSED` (agent attempting `CLOSED` gets `403`).
- Close timestamps and actor attribution are set on `CLOSED`:
  - `closed_at`
  - `closed_by_admin_id`

## 7) Audit trail (what is recorded, where, when)

### 7.1 What is audited

The system writes **status transition history** to `lead_status_history`:

- `from_status` and `to_status`
- `actor_user_id` and `actor_role`
- optional `reason`
- `changed_at` timestamp

### 7.2 When audit records are written

In `LeadService`:

- **On lead creation** (`create_contact_form_lead`, `create_admin_manual_lead`): records `None → NEW`.
- **On status update** (`update_status`): records `previous → target`.
- **On agent reply auto-promotion** in `reply_to_lead`:
  - If the lead is `NEW`, it auto-updates to `IN_PROGRESS` and records the transition with reason `"Auto-promoted after reply"`.

### 7.3 What is not audited (current behavior)

- Lead reassignment does not write to `lead_status_history` (it emits a notification event only).
  - Recommendation is captured below if reassignment should be auditable as a separate table or as an event-style audit row.
- Note create/update/delete and message creation are persisted but not mirrored into a unified audit/event stream.

## 8) Notifications & external side-effects

File: `app/services/lead_notification_service.py`

Current implementation:

- Emits structured log lines for:
  - lead created
  - status changed
  - lead reassigned
  - note added
  - reply sent
- Emits a separate “email hook TODO” log line.

This is explicitly marked TODO and should be considered **non-durable**:

- no queue
- no retry/delivery guarantees
- no user-facing notification center integration in this module yet

## 9) End-to-end flow descriptions (runtime)

### 9.1 Registered user: contact form lead creation

1. Request hits `POST /api/v1/leads/contact-form` (role: `registered_user`).
2. `LeadService.create_contact_form_lead`:
   - Validates actor role (must be registered user).
   - Dedupe check: if same user/property/message within a short time window, returns existing lead payload (idempotent UX).
   - Resolves assignment: `repo.get_property_listing_agent_id(property_id)` (listing agent).
   - Creates `Lead(status=NEW, source=EMAIL_FORM, assigned_agent_id=<listing agent>, message=<...>)`.
   - Writes audit `None → NEW`.
   - Commits transaction.
   - Emits notification hooks (log-based).

### 9.2 Agent: work an assigned lead

1. Agent lists leads: `GET /api/v1/agent/leads` with optional `status`/`source` filters.
2. Agent opens detail: `GET /api/v1/agent/leads/{lead_id}`.
3. Agent can:
   - Update status: `PATCH /api/v1/agent/leads/{lead_id}/status`
     - Permission: must be assigned agent.
     - Workflow: transition must be valid.
     - Audit: writes transition record.
   - Reply: `POST /api/v1/agent/leads/{lead_id}/reply`
     - Persists `lead_messages` row.
     - If current status is `NEW`, auto-promotes to `IN_PROGRESS` and audits it.
   - Add/update/delete notes:
     - Notes persist in `lead_notes`
     - Update/delete requires either admin role or note ownership

### 9.3 Admin: manage scoped leads and closing decision

1. Admin lists scoped leads: `GET /api/v1/admin/leads` (scope via `admin_agent_assignments`).
2. Admin can create manual lead: `POST /api/v1/admin/leads`
   - Must be scoped to the target agent (`ensure_admin_can_manage_agent`).
   - Creates lead with `NEW` and given `source`.
   - Audits `None → NEW`.
3. Admin can reassign: `PATCH /api/v1/admin/leads/{lead_id}/reassign`
   - Must be scoped both to the lead and to the new agent.
   - Updates `assigned_agent_id` and `assigned_by_admin_id`.
4. Admin applies close decision:
   - Endpoint: `POST /api/v1/admin/leads/{lead_id}/close-decision`
   - Implementation: currently uses the same `update_status` path.
   - Enforces workflow and sets close fields when moving to `CLOSED`.
   - Audits transition.

## 10) Error handling behavior (audit findings)

### 10.1 HTTP 403 scope vs workflow errors

- Scope violations are surfaced as `403` (via permission service raising `PermissionError`, mapped to `HTTPException(403)` in service).
- Role mismatch (e.g., non-admin attempting `CLOSED`) is `403`.

### 10.2 Invalid status transitions currently raise server errors

`LeadWorkflowManager.validate_transition` raises `ValueError`. In `LeadService.update_status`, this is not mapped to `4xx`, so it can bubble into a `500`.

Impact:

- Clients may see invalid business transitions as “server error” rather than “bad request”.

Recommendation:

- Catch `ValueError` in `LeadService` (or in the route) and map to `HTTP 400` with a clear message like `"Invalid status transition"`.

## 11) Testing and verification status

### 11.1 Unit tests present

- Workflow: `tests/unit/services/test_lead_workflow_manager.py`
- Permissions: `tests/unit/services/test_lead_permission_service.py`
- Service orchestration: `tests/unit/services/test_lead_service.py`
- Route wiring + dependency overrides: `tests/unit/api/routes/test_leads_routes.py`

### 11.2 Verified behaviors (from tests)

- Contact-form dedupe returns existing lead and does not create a new row.
- Status update:
  - writes audit record
  - does not emit notification on commit failure
  - forbids agent setting `CLOSED`
- Reply auto-promotes `NEW → IN_PROGRESS`.
- Admin manual lead creation calls scope enforcement.
- Admin close decision sets `closed_by_admin_id` and status.

## 12) Security / compliance notes (audit perspective)

- **Primary access control** is role + assignment-scoped enforcement, centralized in `LeadPermissionService`.
- **Audit trail** includes actor and reason fields for status transitions, enabling post-hoc review of state changes.
- **PII considerations**:
  - Contact form accepts `name/email/phoneNumber` but current implementation stores only the message and user linkage; this is lower-risk but may be misaligned with product expectations (see recommendations).

## 13) Findings & recommendations

### 13.1 Correctness and consistency

- Map invalid transitions to `400` instead of `500` by catching workflow `ValueError` in `LeadService.update_status` (and in `reply_to_lead` auto-promotion path if desired).
- Consider auditing **reassignment**:
  - Either add a `lead_assignment_history` table, or write an event/audit record type that captures `from_agent → to_agent` with admin actor.

### 13.2 Product/feature alignment risks

- Contact form fields `name/email/phoneNumber` are validated but not persisted to lead rows.
  - If the intended product behavior is “agent sees contact details even without a linked user”, this will need schema/service changes (separate `lead_contact_snapshot` fields, or a related table).

### 13.3 Operational hardening

- Replace log-only notifications with a durable mechanism (queue/event bus) once the notification center module is ready:
  - emit a stored event
  - deliver in-app + email with retry
  - support idempotency for at-least-once delivery

### 13.4 Observability

- Current module emits notification hooks via logs; consider adding:
  - metrics counters for creates/status transitions/reassigns
  - timing for list queries by scope
  - structured fields (lead_id, status, actor_role) in all lead logs

## 14) Appendix: primary reference files

- API routes: `app/api/v1/routes/leads.py`
- DI wiring: `app/api/v1/deps/leads.py`
- Router integration: `app/api/v1/router.py`
- Service: `app/services/lead_service.py`
- Workflow: `app/services/lead_workflow_manager.py`
- Permissions: `app/services/lead_permission_service.py`
- Audit: `app/services/lead_audit_service.py`
- Notifications: `app/services/lead_notification_service.py`
- Repository: `app/repositories/lead_repository.py`
- Models: `app/models/property_normalized.py`
- Migration: `alembic/versions/0039_add_lead_lifecycle_tables.py`
- Existing docs: `docs/LEAD_API_CONTRACT.md`, `docs/LEAD_MODULE_CHANGELOG.md`, `docs/LEAD_FINAL_VERIFICATION_REPORT.md`
- Tests: `tests/unit/services/test_lead_*.py`, `tests/unit/api/routes/test_leads_routes.py`

