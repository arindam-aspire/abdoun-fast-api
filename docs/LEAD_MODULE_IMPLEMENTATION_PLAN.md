# Lead Module Implementation Plan (Final Review)

## Objective

Implement EP-009 / EP-010 / EP-011 lead workflows without creating parallel implementations for the same feature, while preserving existing architecture and behavior.

This plan enforces:
- Single source of truth (`leads` table, extended in place)
- One canonical implementation path per capability (no duplicate routes/services/models)
- SOLID-aligned design within the current `API -> Service -> Repository` layering
- Backward compatibility for existing dashboard/analytics behavior

---

## Locked Decisions (from Product/Architecture)

- Reuse existing `leads` table and apply additive schema changes.
- Use status model exactly as requirement doc:
  - `NEW`
  - `IN_PROGRESS`
  - `REQUEST_FOR_CLOSE`
  - `CLOSED`
- Phone/WhatsApp leads are manually logged by agent/admin.
- Property unpublish on lead close is controlled by admin flag/setting; audit must persist regardless.
- Reply action triggers in-app notification now; email hook included with TODO for upcoming notification module.
- Admin can operate only on leads tied to agents assigned to that admin.
- Multilingual support deferred; EN only for current phase.

---

## Explicit Out-of-Scope (Do Not Implement)

Do not add the following unless explicitly approved in a later phase:
- Reopen lead flow
- Follow-up tracking
- Priority/scoring
- Soft delete/archive
- Duplicate lead detection
- Tags
- Attachments
- Bulk actions
- Export
- Any extra CRM feature not present in approved scope

---

## No-Duplication Guardrails (Mandatory)

1. **Do not create an `inquiries` domain/table/module.**
   - Use `Lead` as canonical entity.
   - Keep `inquiry_type` only as compatibility metadata where needed.

2. **Do not split lead lifecycle logic across multiple services.**
   - A single `LeadService` owns transitions, permissions, and lifecycle rules.

3. **Do not create overlapping lead endpoints in both `admin.py`/`agents.py` and a new router.**
   - Add dedicated `leads.py` routes and keep role-specific path prefixes.
   - Existing dashboard endpoints remain analytics-only.

4. **Do not duplicate audit paths.**
   - Status transitions and actions write to dedicated lead history/audit records once.

5. **Do not re-implement assignment scope checks in controllers.**
   - Centralize scope checks in service/repository reusable methods.

6. **If lead lifecycle APIs exist in `admin.py` or `agents.py`, move them to `leads.py` and retire old handlers.**
   - Never keep parallel live implementations for the same endpoint behavior.

7. **Contact-form creation must include basic duplicate-submission protection.**
   - Keep this lightweight (idempotency key or short-window dedupe) without adding new product features.

---

## Mandatory Internal Responsibility Split

Use this structure to prevent a God class while keeping one canonical orchestration entry point:

```text
LeadService
 ├── LeadWorkflowManager
 ├── LeadPermissionService
 ├── LeadAuditService
 ├── LeadNotificationService
 └── LeadQueryService (or LeadReadService if needed)
```

### Class-level responsibilities

- `LeadService`
  - Public orchestration entry point for routes.
  - Delegates transition checks, access control, audit writes, notifications.
  - Must stay thin; no heavy embedded permission/transition/audit logic.

- `LeadWorkflowManager`
  - Owns transition matrix and validation.
  - Enforces `CLOSED` terminal behavior.
  - Returns clear domain errors for invalid transitions.
  - Performs no DB writes.

- `LeadPermissionService`
  - Owns agent/admin scope rules and note ownership checks.
  - Prevents permission logic duplication in routes.

- `LeadAuditService`
  - Owns status history write path and lifecycle action audit logging.
  - Guarantees one transition produces one history record.

- `LeadNotificationService`
  - Owns in-app notification dispatch.
  - Exposes email hook/TODO integration point for upcoming notification module.

- `LeadRepository`
  - Query and persistence only.
  - No business policy decisions.

---

## SOLID Application Plan

### Single Responsibility Principle (SRP)
- Routers: transport/auth only, no business decisions.
- `LeadService`: status transition rules, ownership checks, workflow orchestration.
- `LeadRepository`: query/persistence only.
- Notification adapter/interface: delivery dispatch contract only.

### Open/Closed Principle (OCP)
- Use transition map/policy object so new statuses/rules can be added without rewriting route logic.
- Notification channel extension (email/SMS/etc.) through interface, not branching in controller.

### Liskov Substitution Principle (LSP)
- Service depends on repository interfaces/protocols where practical to keep test doubles behaviorally equivalent.

### Interface Segregation Principle (ISP)
- Separate repository read/write concerns where it keeps interfaces lean:
  - listing/filter reads
  - workflow actions (status, reassign, close)
  - notes/messages operations

### Dependency Inversion Principle (DIP)
- `LeadService` depends on abstractions:
  - repository contract
  - notification port
  - settings provider
- Concrete implementations wired through existing app dependency system.

---

## Target Architecture (Aligned to Existing Codebase)

### Existing modules to keep
- `app/models/property_normalized.py` (contains current `Lead`)
- dashboard services/repos/routes for analytics (unchanged behavior)

### New/extended components
- `app/schemas/lead.py`
  - request/response DTOs for create/list/detail/status/reassign/reply/notes
- `app/repositories/lead_repository.py`
  - scoped listing, retrieval, mutation, and history persistence
- `app/services/lead_service.py`
  - canonical lifecycle orchestration and permission checks
- `app/api/v1/routes/leads.py`
  - dedicated endpoints; role-gated
- model updates + alembic migration(s)
  - extend `leads`; add history/notes/messages tables

---

## Data Model Changes (Additive, Backward Compatible)

### Extend `leads` table
- `status` (enum/string constrained to required states)
- `source` (email form, phone, whatsapp, manual admin, etc.)
- `assigned_agent_id` (FK `users.id`)
- `assigned_by_admin_id` (FK `users.id`, nullable)
- `last_activity_at`
- `request_close_at` (nullable)
- `closed_at` (nullable)
- `closed_by_admin_id` (FK `users.id`, nullable)

### New supporting tables
- `lead_status_history`
  - transition record (`from_status`, `to_status`, actor, timestamp, optional reason)
- `lead_notes`
  - internal notes with creator ownership and timestamps
- `lead_messages`
  - outbound reply records and delivery channel metadata

### Settings (for property close behavior)
- Add/reuse admin settings source with flag:
  - `auto_unpublish_property_on_lead_close` (bool, default `false`)

### Indexes (performance + query safety)
- `leads(assigned_agent_id, status, created_at)`
- `leads(source, created_at)`
- `lead_status_history(lead_id, changed_at)`
- `lead_notes(lead_id, created_at)`

---

## API Plan (Single Canonical Surface)

### Contact-form ingestion (authenticated user)
- `POST /api/v1/leads/contact-form`
  - Validates fields from requirement
  - Creates lead with:
    - `status=NEW`
    - `source=EMAIL_FORM`
    - assigned listing agent
  - Writes history + emits notification event
  - Applies basic duplicate-submission protection (short-window dedupe/idempotency)

### Agent lead management
- `GET /api/v1/agent/leads`
- `GET /api/v1/agent/leads/{lead_id}`
- `PATCH /api/v1/agent/leads/{lead_id}/status`
  - allowed: `NEW -> IN_PROGRESS`, `IN_PROGRESS -> REQUEST_FOR_CLOSE`
- `POST /api/v1/agent/leads/{lead_id}/reply`
- `POST /api/v1/agent/leads/{lead_id}/notes`
- `PATCH /api/v1/agent/leads/{lead_id}/notes/{note_id}`
- `DELETE /api/v1/agent/leads/{lead_id}/notes/{note_id}`

### Admin lead management (scoped to assigned agents only)
- `GET /api/v1/admin/leads`
- `POST /api/v1/admin/leads` (manual phone/WhatsApp/admin leads)
- `PATCH /api/v1/admin/leads/{lead_id}/reassign`
- `PATCH /api/v1/admin/leads/{lead_id}/status`
- `POST /api/v1/admin/leads/{lead_id}/close-decision` (approve/reject request close)

---

## Lifecycle & Transition Rules (Canonical Matrix)

- `NEW -> IN_PROGRESS`
  - Actor: assigned agent or eligible admin
- `IN_PROGRESS -> REQUEST_FOR_CLOSE`
  - Actor: assigned agent or eligible admin
- `REQUEST_FOR_CLOSE -> CLOSED`
  - Actor: eligible admin only
- `CLOSED` is terminal unless explicit reopen policy is approved later.

All transitions must:
- validate actor authorization and scope
- persist transition in `lead_status_history`
- update `leads.last_activity_at`
- emit in-app notification event
- emit email notification intent (TODO adapter implementation)

---

## Access Control & Scope Enforcement

### Agent
- Can access only leads where `assigned_agent_id == current_user.id`.

### Admin
- Can access only leads where `assigned_agent_id` belongs to active assignments of that admin.
- Scope resolved via `admin_agent_assignments`.

### Notes permissions
- Note update/delete allowed for note creator or admin in allowed scope.

---

## Validation Rules (EN only)

For contact form (`POST /leads/contact-form`):
- Name: 2-20 chars
- Email: valid format
- Phone: valid country-code-aware format (project standard)
- Message: 10-1000 chars

For replies:
- non-empty
- max length bounded by schema constant

For manual phone/WhatsApp leads:
- `source` required and constrained
- property + assignee + contact identity required

---

## Notification Strategy

### Current phase
- In-app notification events persist and dispatch through existing notification plumbing where available.

### Email integration
- Add service-level hook and event payload now.
- Mark concrete email dispatch in lead flows as TODO until notification module enhancement is delivered.

This avoids rework and preserves single orchestration point.

---

## Backward Compatibility & Regression Safety

- Keep existing dashboard/analytics endpoints behavior unchanged.
- Keep legacy `inquiry_type` usage readable while introducing canonical `source`.
- Add backfill to map legacy rows to new status/source defaults.
- No destructive migration in phase 1.

---

## Delivery Phases

### Phase 1: Schema + Models (additive only)
- Alembic migration for new columns/tables/indexes
- SQLAlchemy model updates
- Backfill defaults for existing rows

### Phase 2: Repository + Service core
- Lead repository methods
- Lead service transition enforcement
- Scope checks and audit/history persistence

### Phase 3: API routes + validation
- Add `leads.py` routes
- Request/response schemas
- Role and scope guards

### Phase 4: Notifications + property close flag behavior
- in-app events wired
- email hook TODO integrated
- optional property unpublish controlled by admin flag and fully audited

### Phase 5: Test hardening + regression
- unit, repository, and route tests
- regression checks for dashboard/leaderboard

---

## Execution Workflow (Required)

### Step 1 - Understanding report (before code changes)
- Validate current lead-related models/schemas/routes/services/repositories.
- Confirm existing dashboard/inquiry analytics behavior that must remain stable.
- Confirm auth/role/admin-assignment/notification patterns.
- Confirm response envelope and pagination conventions.
- Confirm test structure and placement.

### Step 2 - API verification against approved surface
For each expected endpoint, classify as:
- existing and reusable
- existing but requires modification
- missing and needs implementation
- should not be created (duplicate risk)

Additionally:
- If overlapping lead endpoints are found in `admin.py` or `agents.py`, migrate to `leads.py` and remove duplicate implementations.

### Step 3 - Implement with checklist discipline
- Execute one checklist item at a time.
- Validate each item before moving forward.
- Do not mix unrelated items in a single change.

### Step 4 - Final implementation note
Produce implementation note with:
- files changed
- classes added/modified
- APIs confirmed/added/changed
- tests added/updated and execution results
- behavior intentionally unchanged
- TODO left for notification/email module

---

## Checklist (Execution-Ready)

1. **Baseline verification**
   - Files: lead model, dashboard repos/services/routes, permissions, notification service, route response helpers.
   - Expected: clear no-break map of existing behavior and reusable patterns.
   - Validation: repository scan + route contract check.
   - Rollback: N/A (analysis-only).

2. **Schema extension + migration (additive)**
   - Files: `alembic/versions/*`, lead model definitions.
   - Expected: new lead lifecycle fields and support tables with indexes; no destructive changes.
   - Validation: run migration upgrade locally and schema inspection.
   - Rollback: downgrade migration and remove added revision.

3. **Repository scaffolding and scoped query centralization**
   - Files: `app/repositories/lead_repository.py` (+ minimal shared query helpers).
   - Expected: single scope-aware query path for agent/admin reads and writes.
   - Validation: repository unit tests for scope and filters.
   - Rollback: keep old paths untouched, revert new repository file and wiring.

4. **Workflow/permission/audit/notification service split**
   - Files: `app/services/lead_service.py`, `lead_workflow_manager.py`, `lead_permission_service.py`, `lead_audit_service.py`, `lead_notification_service.py`.
   - Expected: `LeadService` orchestration-only; policy logic delegated.
   - Validation: unit tests for transitions/permissions/audit calls/notification triggers.
   - Rollback: revert split files and preserve prior service behavior.

5. **Route implementation (canonical surface only)**
   - Files: `app/api/v1/routes/leads.py`, router registration.
   - Expected: approved endpoint set only; no duplicate endpoints in unrelated route files; overlapping lead handlers migrated out of `admin.py`/`agents.py`.
   - Validation: route tests for success/failure/authorization.
   - Rollback: unregister router and revert route file.

6. **Notification TODO hook and admin property-close flag behavior**
   - Files: lead service + settings access + property state integration path.
   - Expected: in-app notifications active; email hook present but TODO-safe; property unpublish controlled by flag and audited.
   - Validation: unit/integration tests around flag-on/flag-off behavior.
   - Rollback: disable feature flag integration path.

7. **Regression hardening**
   - Files: tests for dashboard/analytics stability.
   - Expected: existing dashboard/leaderboard behavior unchanged.
   - Validation: targeted test suite + route coverage checks.
   - Rollback: revert offending query/service changes only.

8. **Duplicate-submission safeguard for contact form**
   - Files: lead service/repository + request handling path.
   - Expected: repeated same payload in short window does not create duplicate leads.
   - Validation: integration test with repeated submit.
   - Rollback: disable safeguard behind simple feature toggle if urgent.

---

## Test Plan (Must Pass)

1. **Unit tests**
   - transition rule enforcement
   - forbidden transitions
   - admin scope filtering
   - note ownership permissions

2. **Repository tests**
   - list filters (status/source/date/agent)
   - assignment-scoped admin queries
   - transition/history persistence

3. **Integration/API tests**
   - contact-form lead creation (auth required)
   - agent workflow end-to-end
   - admin manual phone/WhatsApp creation
   - reassign and close-decision flow
   - unauthorized cross-scope access blocked

4. **Regression tests**
   - existing dashboard and leaderboard routes unaffected

---

## Risks and Controls

- Risk: accidental parallel inquiry implementation  
  - Control: explicit rule to keep `Lead` canonical and reject new inquiry domain artifacts.

- Risk: permission leakage across admins  
  - Control: mandatory scope join via `admin_agent_assignments` in repository methods.

- Risk: analytics drift after schema extension  
  - Control: keep compatibility fields and migrate analytics usage gradually.

- Risk: notification inconsistency  
  - Control: centralize events in service and defer channel-specific adapter completion cleanly.

---

## Definition of Done for This Implementation

- No duplicate lead/inquiry module introduced.
- New lead lifecycle endpoints implemented through one service/repository path.
- Required status flow and permissions enforced exactly as approved.
- Admin assignment scope enforced in every admin lead action.
- Audit history persisted for all transitions and key actions.
- Property close behavior uses configurable admin flag and is auditable.
- Tests for new behavior and regression are green.

