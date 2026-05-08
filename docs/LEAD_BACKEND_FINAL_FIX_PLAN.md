# Lead Backend Final Fix Plan (SOLID + Canonical APIs)

Date: 2026-05-06  
Scope: Backend only (`app/api/v1/routes/leads.py` → `LeadService` → `LeadRepository` + allowed internal services)  
Core rule: **Do not create separate APIs only because the actor role is different.** If action/resource is the same, create **one canonical endpoint** and enforce role/permission in service logic.

## Step 1 — Current State Inspection

### Current route map (Lead Management)

Registered user (public router, authenticated as `registered_user`):
- `POST /api/v1/leads/contact-form`

Agent router (prefixed by `/api/v1/agent`):
- `GET /api/v1/agent/leads`
- `GET /api/v1/agent/leads/{lead_id}`
- `PATCH /api/v1/agent/leads/{lead_id}/status`
- `POST /api/v1/agent/leads/{lead_id}/reply` (creates a `lead_messages` row)
- `POST /api/v1/agent/leads/{lead_id}/notes`
- `PATCH /api/v1/agent/leads/{lead_id}/notes/{note_id}`
- `DELETE /api/v1/agent/leads/{lead_id}/notes/{note_id}`

Admin router (prefixed by `/api/v1/admin`):
- `GET /api/v1/admin/leads`
- `POST /api/v1/admin/leads`
- `PATCH /api/v1/admin/leads/{lead_id}/reassign`
- `PATCH /api/v1/admin/leads/{lead_id}/status`
- `POST /api/v1/admin/leads/{lead_id}/close-decision`

### Existing duplicates / role-split APIs

- **Lead detail** exists only as role-specific: `GET /api/v1/agent/leads/{lead_id}` (no shared `GET /api/v1/leads/{lead_id}`).
- **Messages** exist only as an agent-only “reply” action: `POST /api/v1/agent/leads/{lead_id}/reply` (no shared messages collection; no admin read; no registered user read/post).
- **Notes** exist only under agent router (admin/registered user do not have shared endpoints).
- **History** not exposed by any route.
- **Status transition** is shared in service (`LeadService.update_status`) but exposed via role endpoints.

### Known requirement gaps vs current behavior

- **Invalid transition → HTTP 400**: workflow raises `ValueError`; current service does not map it → likely becomes `500`.
- **Registered user lead list** missing (`GET /api/v1/leads/my` required).
- **Shared canonical endpoints** missing: lead detail, messages, notes, history under `/api/v1/leads/...`.
- **Admin full access**: current `LeadPermissionService` restricts admin to agents linked in `admin_agent_assignments`. Requirement says admin should have full access unless tiers exist.
- **Property unpublish on CLOSED**: `LeadService.update_status` contains a TODO and currently does nothing.
- **Durable in-app notifications**: `LeadNotificationService` is log-only; no obvious notification-center persistence exists in repo.
- **Assignment/SLA helpers**: not implemented; can be introduced only if required now.

## Proposed Canonical API Surface (Final Target)

### Keep (as-is)

- `POST /api/v1/leads/contact-form` (canonical)
- `GET /api/v1/agent/leads` (role-based list may remain)
- `GET /api/v1/admin/leads` (role-based list may remain)
- `PATCH /api/v1/agent/leads/{lead_id}/status` (may remain)
- `POST /api/v1/admin/leads/{lead_id}/close-decision` (canonical close decision)

### Add canonical shared endpoints (preferred)

- **Registered user list**
  - `GET /api/v1/leads/my`

- **Shared lead detail**
  - `GET /api/v1/leads/{lead_id}`

- **Shared messages**
  - `GET /api/v1/leads/{lead_id}/messages`
  - `POST /api/v1/leads/{lead_id}/messages`

- **Shared notes**
  - `GET /api/v1/leads/{lead_id}/notes`
  - `POST /api/v1/leads/{lead_id}/notes`
  - `PATCH /api/v1/leads/{lead_id}/notes/{note_id}`
  - `DELETE /api/v1/leads/{lead_id}/notes/{note_id}`

- **Shared history**
  - `GET /api/v1/leads/{lead_id}/history`

### Compatibility wrappers to keep (delegate to canonical service methods)

- Keep `GET /api/v1/agent/leads/{lead_id}` as wrapper delegating to `LeadService.get_lead_detail(...)`.
- Keep `POST /api/v1/agent/leads/{lead_id}/reply` as wrapper delegating to canonical `POST /api/v1/leads/{lead_id}/messages`.
- Keep existing admin status endpoints as wrappers delegating to the same transition method used by agent status and close decision.

### APIs to retire/remove (Lead Management only)

None removed immediately in first pass; prefer **deprecate-only** by:
- leaving wrappers intact for compatibility,
- updating docs to prefer canonical shared endpoints,
- adding tests to ensure wrappers call the same service logic.

## Permission/Service Rules (Canonical Behavior)

### Lead detail `GET /api/v1/leads/{lead_id}`

- `registered_user`: can read only if `lead.user_id == actor.id`
- `agent`: can read only if `lead.assigned_agent_id == actor.id`
- `admin`: **full access to all leads** (unless project later introduces explicit admin tiers)

### Messages `GET/POST /api/v1/leads/{lead_id}/messages`

- `registered_user`: can read/post only on own lead
- `agent`: can read/post only on assigned lead
- `admin`: can read all messages, **must not edit/delete** user/agent messages (no edit/delete endpoints)

### Notes `.../notes`

- `registered_user`: forbidden
- `agent`: assigned lead only; can update/delete **own notes only**
- `admin`: can view/add notes; update/delete rules must follow requirement (default: admin can manage notes)

### History `GET /api/v1/leads/{lead_id}/history`

- `registered_user`: forbidden
- `agent`: assigned lead only
- `admin`: full access

### Status / Close

- Invalid transition → `400`
- Permission issue → `403`
- `CLOSED` allowed only via admin close decision (service-level enforcement)
- Closing must also **unpublish property** (implementation described below)

## Impacted Files (Expected)

Routes / deps:
- `app/api/v1/routes/leads.py` (add canonical shared routers + wrappers delegations)
- `app/api/v1/router.py` (wire new shared lead router paths under `/api/v1/leads/...` without role-prefix)
- `app/api/v1/deps/leads.py` (if new helpers added)

Service / policy:
- `app/services/lead_service.py` (add list-my, messages list/create, notes list, history list; map invalid transition to 400; property unpublish on close)
- `app/services/lead_permission_service.py` (add registered-user scope; adjust admin “full access”)
- `app/services/lead_workflow_manager.py` (no change expected to transitions list)
- `app/services/lead_notification_service.py` (replace log-only only if durable infra exists; otherwise document gap)

Repository / models:
- `app/repositories/lead_repository.py` (query methods for messages/notes/history/user-leads; property unpublish update)
- `app/schemas/lead.py` (add DTOs for message list and history if needed)

Tests:
- `tests/unit/api/routes/test_leads_routes.py` (new routes + wrappers)
- `tests/unit/services/test_lead_service.py` (invalid transition → 400; user access; close unpublishes property; notification only after commit)
- `tests/unit/services/test_lead_permission_service.py` (registered-user scope; admin full access; note ownership; forbiddens)
- add new tests for messages/notes/history behavior as required.

Docs:
- `docs/LEAD_API_CONTRACT.md` (update to canonical surface + wrappers)
- `docs/LEAD_MANAGEMENT_AUDIT_REPORT.md` (final alignment summary or pointer)
- Create final report: `docs/LEAD_BACKEND_FINAL_IMPLEMENTATION_REPORT.md`

## Migration Needs

- No DB migration required for canonical routing itself (tables already exist: `lead_messages`, `lead_notes`, `lead_status_history`).
- If durable in-app notification persistence is implemented, it may require a new table/migration (only if infra exists or is approved as in-scope).

## Risks / Non-goals

- **Admin “full access”** conflicts with current `admin_agent_assignments` scope model; recommended approach is to treat current scope restriction as an “admin tier” feature flag and default to full access to meet requirement.
- **Durable notifications**: repo currently appears log-only for Lead notifications; if no existing persistence layer exists, this requirement must be marked as blocked/needs infra.
- **Assignment round-robin & SLA**: not present; introduce only if explicitly required now, otherwise keep as deferred additions.

---

## Requirement Alignment Table

| Requirement | Existing Behavior | Proposed Design | API Decision | Files Impacted | Priority |
|---|---|---|---|---|---|
| Keep contact form `POST /leads/contact-form` | Exists, registered-user only | Keep as canonical | no API change needed | `app/api/v1/routes/leads.py`, `LeadService` | P0 |
| Registered user list `GET /leads/my` | Missing | Add list of own leads | canonical shared endpoint | `routes/leads.py`, `lead_service.py`, `lead_repository.py`, tests, contract docs | P0 |
| Shared lead detail `GET /leads/{id}` | Only agent detail exists | Add shared endpoint; role-based access in service | canonical shared endpoint | `routes/leads.py`, `lead_permission_service.py`, tests, contract docs | P0 |
| Agent/admin detail endpoints | Agent detail exists | Keep as wrapper delegating to shared detail method | existing role endpoint retained as wrapper | `routes/leads.py`, tests | P1 |
| Shared messages `GET/POST /leads/{id}/messages` | Only agent `POST .../reply` | Add shared messages endpoints; keep `/reply` wrapper | canonical shared endpoint | `routes/leads.py`, `lead_service.py`, `lead_repository.py`, `schemas/lead.py`, tests, docs | P0 |
| Agent reply endpoint | Exists | Keep as compatibility wrapper → messages create | existing role endpoint retained as wrapper | `routes/leads.py`, tests, docs | P1 |
| Shared notes `GET/POST/PATCH/DELETE /leads/{id}/notes...` | Agent-only notes endpoints exist | Add shared notes endpoints with role rules; keep agent endpoints as wrappers or keep as-is | canonical shared endpoint | `routes/leads.py`, `lead_service.py`, `lead_permission_service.py`, `lead_repository.py`, tests, docs | P0 |
| Shared history `GET /leads/{id}/history` | Missing | Add shared history endpoint based on `lead_status_history` | canonical shared endpoint | `routes/leads.py`, `lead_service.py`, `lead_repository.py`, `schemas/lead.py`, tests, docs | P0 |
| Invalid transition returns 400 | Currently likely 500 | Catch workflow `ValueError` → raise `HTTPException(400)` | no API change needed | `lead_service.py`, tests | P0 |
| Admin full access to all leads | Admin is scope-restricted | Default admin to full access; keep scoped mode behind setting if needed | no API change needed | `lead_permission_service.py`, tests, docs | P0 |
| Close unpublishes property | TODO / not implemented | On `CLOSED`, soft-delete/unpublish property via repository update | no API change needed | `lead_service.py`, `lead_repository.py`, tests | P0 |
| Durable in-app notification | Log-only | Implement only if infra exists; otherwise document blocked | no API change needed | `lead_notification_service.py` (maybe), docs | P2 |
| Assignment configurable + RR default | Not implemented | Add `LeadAssignmentService` only if required now; default RR | no API change needed | new `lead_assignment_service.py` + `lead_service.py` + tests | P2 |
| SLA config + breach flagging | Not implemented | Add `LeadSLAService` only if required now | no API change needed | new `lead_sla_service.py` + service/repo/tests | P2 |
| Remove/deprecate duplicate lead APIs | Not applicable yet | Prefer canonical + keep wrappers, mark deprecated in docs | removed/deprecated duplicate | docs + route wrappers | P1 |
| Update API contract + final report | Partial contract exists | Update contract and produce final implementation report | no API change needed | `docs/LEAD_API_CONTRACT.md`, new report docs | P0 |

## Step 3 — Implementation Checklist (small, reviewable)

Each item includes files, expected behavior, tests, validation, rollback.

1) **Map invalid status transitions to HTTP 400**
   - Files: `app/services/lead_service.py`, tests in `tests/unit/services/test_lead_service.py`
   - Behavior: invalid transition raises `HTTPException(status_code=400)`; permission failures remain `403`
   - Tests: “invalid transition returns 400”
   - Validate: `pytest -q`
   - Rollback: revert mapping change; rely on current exception bubbling

2) **Add registered user list `GET /api/v1/leads/my`**
   - Files: `app/api/v1/routes/leads.py`, `app/services/lead_service.py`, `app/repositories/lead_repository.py`, `tests/unit/api/routes/test_leads_routes.py`
   - Behavior: registered user receives only their own leads; pagination aligned with existing list responses
   - Tests: “registered user can view own lead list”
   - Validate: `pytest -q`
   - Rollback: remove route + methods

3) **Add shared lead detail `GET /api/v1/leads/{lead_id}` + permissions**
   - Files: `routes/leads.py`, `lead_permission_service.py`, `lead_service.py`, tests
   - Behavior: registered user only own; agent only assigned; admin full access
   - Tests: “registered user can view own lead”, “cannot view another user’s lead”, “admin full access”
   - Validate: `pytest -q`
   - Rollback: keep role-specific detail only

4) **Add shared messages `GET/POST /leads/{lead_id}/messages` and keep `/agent/.../reply` wrapper**
   - Files: `routes/leads.py`, `lead_service.py`, `lead_repository.py`, `schemas/lead.py`, tests
   - Behavior: user/agent post allowed by scope; admin read all; no edit/delete
   - Tests: “user can post message on own lead”, “agent can post message on assigned lead”, “admin can read all messages”, “wrappers delegate to same service logic”
   - Validate: `pytest -q`
   - Rollback: keep agent-only reply endpoint

5) **Add shared notes endpoints + forbid registered user**
   - Files: `routes/leads.py`, `lead_service.py`, `lead_permission_service.py`, `lead_repository.py`, tests
   - Behavior: registered user forbidden; agent ownership enforced; admin view/add
   - Tests: “notes forbidden for registered user”, “agent note ownership enforced”, “admin can view/add notes”
   - Validate: `pytest -q`
   - Rollback: keep agent-only notes endpoints

6) **Add shared history `GET /leads/{lead_id}/history`**
   - Files: `routes/leads.py`, `lead_service.py`, `lead_repository.py`, `schemas/lead.py`, tests
   - Behavior: agent sees assigned; admin sees all; registered user forbidden
   - Tests: “agent can view assigned lead history”, “admin can view all lead history”
   - Validate: `pytest -q`
   - Rollback: remove history route

7) **Close unpublishes property**
   - Files: `lead_service.py`, `lead_repository.py`, tests
   - Behavior: when transitioning to `CLOSED`, property is unpublished via soft-delete (set `properties_normalized.deleted_at` + reason) or equivalent existing unpublish mechanism; only after successful transaction
   - Tests: “close unpublishes property”, “notification created only after successful transaction”
   - Validate: `pytest -q`
   - Rollback: revert unpublish step

8) **Docs updates + final implementation report**
   - Files: `docs/LEAD_API_CONTRACT.md`, new `docs/LEAD_BACKEND_FINAL_IMPLEMENTATION_REPORT.md`, update audit report if needed
   - Behavior: canonical surface documented; wrappers listed; deprecated endpoints marked
   - Tests: N/A (doc validation via review)
   - Validate: `python -m compileall app` (optional) + `pytest -q`
   - Rollback: revert docs changes only

