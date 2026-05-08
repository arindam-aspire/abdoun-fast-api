# Lead Backend Cleanup Verification Report

Date: 2026-05-06  
Scope reviewed: Lead Management backend only

## Route Matrix

Canonical shared endpoints (verified present):
- `GET /api/v1/leads/my`
- `GET /api/v1/leads/{lead_id}`
- `GET /api/v1/leads/{lead_id}/messages`
- `POST /api/v1/leads/{lead_id}/messages`
- `GET /api/v1/leads/{lead_id}/notes`
- `POST /api/v1/leads/{lead_id}/notes`
- `PATCH /api/v1/leads/{lead_id}/notes/{note_id}`
- `DELETE /api/v1/leads/{lead_id}/notes/{note_id}`
- `GET /api/v1/leads/{lead_id}/history`

Role endpoints retained (verified present):
- `GET /api/v1/agent/leads/{lead_id}`
- `POST /api/v1/agent/leads/{lead_id}/reply`
- `POST /api/v1/agent/leads/{lead_id}/notes`
- `PATCH /api/v1/agent/leads/{lead_id}/notes/{note_id}`
- `DELETE /api/v1/agent/leads/{lead_id}/notes/{note_id}`
- `PATCH /api/v1/admin/leads/{lead_id}/status`
- `POST /api/v1/admin/leads/{lead_id}/close-decision`

## Wrappers Retained

Confirmed compatibility wrappers (thin route -> shared service method):
- `GET /api/v1/agent/leads/{lead_id}` -> `LeadService.get_lead_detail(...)`
- `POST /api/v1/agent/leads/{lead_id}/reply` -> `LeadService.post_message(...)`
- Agent notes endpoints -> `LeadService.add_note/update_note/delete_note(...)`
- Admin status and close-decision endpoints -> `LeadService.update_status(...)`

## Verification Findings

- Canonical APIs required by cleanup checklist exist.
- No duplicate permission logic in routes: route role guards only; lead/resource permission rules stay in `LeadService` + `LeadPermissionService`.
- No duplicate workflow logic in routes: transition checks remain in `LeadWorkflowManager` via `LeadService.update_status`.
- No duplicate close logic in routes: both admin status/close routes call the same `LeadService.update_status`.
- Admin close/status does not bypass internals:
  - status transition validation
  - audit (`LeadAuditService.record_status_transition`)
  - notifications (`LeadNotificationService.emit_lead_event` / email hook)
  - property unpublish on `CLOSED` (`LeadRepository.unpublish_property_on_lead_close`)

## Code Removed

Removed unused old Lead-repository code that no longer participates in canonical flow:
- `LeadRepository.list_admin_scoped_leads(...)`
- `LeadRepository.is_admin_scoped_to_agent(...)`
- corresponding unused imports in `lead_repository.py`

Rationale:
- both methods were no longer referenced after admin full-access alignment.
- removal does not affect wrappers or canonical endpoints.

## Code Deprecated

- No additional runtime code deprecated in this cleanup pass.
- Existing compatibility wrappers are intentionally retained for frontend safety.

## OpenAPI Verification

OpenAPI check executed from app runtime confirmed all required canonical and wrapper paths are registered:
- command output: `MISSING []`

## Tests Run

- `pytest -q tests/unit/services/test_lead_workflow_manager.py` -> `3 passed`
- `pytest -q tests/unit/services/test_lead_permission_service.py` -> `6 passed`
- `pytest -q tests/unit/services/test_lead_service.py` -> `13 passed`
- `pytest -q tests/unit/api/routes/test_leads_routes.py` -> `13 passed`

## Scope Confirmation

- Cleanup changes in this verification task touched only Lead Management backend code and this report.
- No frontend files were touched.
- No unrelated module changes were introduced by this cleanup step.
- No `CONNECTED` status was added.

