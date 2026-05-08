# Lead Module Change Log

## Scope

This document summarizes the implemented backend changes for Lead Management, aligned with:
- `docs/LEAD_MODULE_IMPLEMENTATION_PLAN.md`
- Approved constraints (no extra CRM features, no duplicate implementation paths)

---

## 1) Database and ORM Changes

### New migration
- `alembic/versions/0039_add_lead_lifecycle_tables.py`

### `leads` table extensions (additive)
- `status` (`lead_status_enum`: `NEW`, `IN_PROGRESS`, `REQUEST_FOR_CLOSE`, `CLOSED`)
- `source` (`lead_source_enum`: `EMAIL_FORM`, `PHONE`, `WHATSAPP`, `MANUAL_ADMIN`)
- `assigned_agent_id` (FK -> `users.id`)
- `assigned_by_admin_id` (FK -> `users.id`)
- `last_activity_at`
- `request_close_at`
- `closed_at`
- `closed_by_admin_id` (FK -> `users.id`)

### New supporting tables
- `lead_status_history`
- `lead_notes`
- `lead_messages`

### Indexes added
- `ix_leads_status`
- `ix_leads_source`
- `ix_leads_assigned_agent_id`
- `ix_leads_agent_status_created`
- `ix_leads_source_created`
- `lead_status_history`/`lead_notes`/`lead_messages` time and lookup indexes

### ORM model updates
- Updated `app/models/property_normalized.py`:
  - Extended `Lead`
  - Added `LeadStatusHistory`
  - Added `LeadNote`
  - Added `LeadMessage`

---

## 2) Repository Layer

### New file
- `app/repositories/lead_repository.py`

### Implemented responsibilities
- Scope-aware lead listing:
  - Agent-only leads (`assigned_agent_id == actor.id`)
  - Admin-scoped leads (through active `admin_agent_assignments`)
- Lead retrieval and create operations
- Status history persistence
- Notes persistence (create/get/delete)
- Lead reply message persistence
- Contact-form duplicate-submission detection (short-window dedupe)
- Transaction helpers (`commit`, `rollback`)

---

## 3) Service Layer (SOLID Split)

### New files
- `app/services/lead_workflow_manager.py`
- `app/services/lead_permission_service.py`
- `app/services/lead_audit_service.py`
- `app/services/lead_notification_service.py`
- `app/services/lead_service.py`

### Service split summary
- **LeadService**: single orchestration entry point
- **LeadWorkflowManager**: status transition policy and validation
- **LeadPermissionService**: scope checks (agent/admin) + note ownership checks
- **LeadAuditService**: centralized transition history writes
- **LeadNotificationService**: in-app event emission + email hook TODO

### Status transitions implemented
- `NEW -> IN_PROGRESS`
- `IN_PROGRESS -> REQUEST_FOR_CLOSE`
- `REQUEST_FOR_CLOSE -> CLOSED`
- `CLOSED` terminal (no reopen implemented)

---

## 4) API Layer

### New dependency module
- `app/api/v1/deps/leads.py`

### New route module
- `app/api/v1/routes/leads.py`

### Added endpoints

#### Contact form
- `POST /api/v1/leads/contact-form`

#### Agent lead management
- `GET /api/v1/agent/leads`
- `GET /api/v1/agent/leads/{lead_id}`
- `PATCH /api/v1/agent/leads/{lead_id}/status`
- `POST /api/v1/agent/leads/{lead_id}/reply`
- `POST /api/v1/agent/leads/{lead_id}/notes`
- `PATCH /api/v1/agent/leads/{lead_id}/notes/{note_id}`
- `DELETE /api/v1/agent/leads/{lead_id}/notes/{note_id}`

#### Admin lead management
- `GET /api/v1/admin/leads`
- `POST /api/v1/admin/leads`
- `PATCH /api/v1/admin/leads/{lead_id}/reassign`
- `PATCH /api/v1/admin/leads/{lead_id}/status`
- `POST /api/v1/admin/leads/{lead_id}/close-decision`

### Router integration
- Updated `app/api/v1/router.py` to include lead routers.
- Updated `app/utils/constants.py` with lead route/tag constants.

---

## 5) Schema Contracts

### New file
- `app/schemas/lead.py`

Includes request/response models for:
- Contact form creation
- Manual admin lead creation
- Status update
- Reassign
- Reply
- Notes create/update
- Lead list and detail payloads

---

## 6) No-Duplication and Scope Controls Applied

- Reused canonical `Lead` entity (no `inquiries` module introduced)
- Single orchestration service (`LeadService`)
- Centralized transition logic, permissions, audit, notifications
- Admin scope enforced through `admin_agent_assignments`
- Contact-form duplicate-submission protection added

---

## 7) Swagger / OpenAPI Status

Swagger is updated automatically via FastAPI route/schema registration.

Verified lead routes are present in OpenAPI:
- `/api/v1/leads/contact-form`
- `/api/v1/agent/leads`
- `/api/v1/agent/leads/{lead_id}`
- `/api/v1/agent/leads/{lead_id}/status`
- `/api/v1/agent/leads/{lead_id}/reply`
- `/api/v1/agent/leads/{lead_id}/notes`
- `/api/v1/agent/leads/{lead_id}/notes/{note_id}`
- `/api/v1/admin/leads`
- `/api/v1/admin/leads/{lead_id}/reassign`
- `/api/v1/admin/leads/{lead_id}/status`
- `/api/v1/admin/leads/{lead_id}/close-decision`

---

## 8) Tests Added and Validation Run

### Added tests
- `tests/unit/services/test_lead_workflow_manager.py`
- `tests/unit/services/test_lead_service.py`
- `tests/unit/api/routes/test_leads_routes.py`

### Executed tests
- `python -m pytest tests/unit/services/test_admin_dashboard_service.py -q` -> passed
- `python -m pytest tests/unit/services/test_agent_dashboard_service.py -q` -> passed
- `python -m pytest tests/unit/services/test_agent_service.py -q` -> passed
- `python -m pytest tests/unit/services/test_lead_workflow_manager.py tests/unit/services/test_lead_service.py tests/unit/api/routes/test_leads_routes.py -q` -> passed
- `python -m pytest tests/test_routes_coverage.py tests/unit/services/test_admin_dashboard_service.py tests/unit/services/test_agent_dashboard_service.py tests/unit/services/test_agent_service.py -q` -> passed

Linter diagnostics checked for changed files: no issues reported.

---

## 9) Migration and Deployment Steps

### Required
1. Run DB migration:
   - `alembic upgrade head`
2. Confirm revision:
   - `alembic heads` should show `0039_lead_lifecycle`

### Recommended smoke checks (post-deploy)
1. Open Swagger docs and verify lead endpoints are visible.
2. Validate flows:
   - Contact-form lead creation
   - Agent list/detail/status update
   - Admin manual create/reassign/close-decision
3. Verify audit rows are created for transitions.

---

## 10) Known TODOs / Deferred by Design

- Email dispatch for lead notifications remains a TODO hook in `LeadNotificationService`.
- Property unpublish action on lead close is left as a controlled hook pending full admin setting/property-state integration.
- No reopen/priority/tags/attachments/export/bulk actions added (by approved scope).

