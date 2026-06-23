# Phase 6 Completion Status - Lead and Inquiry Workflow

Date: 2026-06-24

## Scope Completed

Phase 6 implements the MVP lead/inquiry workflow using the live lead tables already present in the test database.

Implemented backend endpoints:

- `POST /api/v1/leads`
- `GET /api/v1/leads`
- `GET /api/v1/leads/{lead_id}`
- `PATCH /api/v1/leads/{lead_id}/assign`
- `PATCH /api/v1/leads/{lead_id}/status`
- `POST /api/v1/leads/{lead_id}/request-close`
- `POST /api/v1/leads/{lead_id}/close`
- `POST /api/v1/leads/{lead_id}/notes`
- `POST /api/v1/leads/{lead_id}/messages`

## Business Rules Implemented

- Public or authenticated users can create an inquiry against an active public property.
- Authenticated inquiry creation links the lead to the requesting user.
- Public/guest inquiry creation stores contact details on the lead record.
- Agency Admin can view agency leads, assign leads to agents, and close leads.
- Agent can view assigned leads, add notes/messages, and request lead closure.
- Registered users can view their own leads.
- Super Admin can view all leads.
- Lead status lifecycle uses the live DB enum values:
  - `NEW`
  - `IN_PROGRESS`
  - `REQUEST_FOR_CLOSE`
  - `CLOSED`
- Assignment moves a `NEW` lead to `IN_PROGRESS`.
- Agent close request moves a lead to `REQUEST_FOR_CLOSE`.
- Agency Admin close approval moves a lead to `CLOSED`.
- Closed leads cannot be changed further.
- Status changes are written to `lead_status_history`.
- Notes are written to `lead_notes`.
- Messages are written to `lead_messages`.
- Activity records are written for lead creation, assignment, and status changes.
- In-app notifications are created for lead creation, assignment, and messages.
- Email and SMS behavior remains log-only in dev mode, as confirmed.

## Implementation Notes

- This phase intentionally does not close the property or remove it from public search. Property deal closure is a separate workflow and remains for the next phase.
- SMS lead messages are supported at API level, but because the live `lead_messages.channel` enum only supports `IN_APP` and `EMAIL`, SMS messages are logged and persisted as `IN_APP` with `delivery_state = logged`.
- Lead numbers are generated in the format `LD-YYYYMMDD-#####`.
- Lead visibility is role-aware and agency-scoped through `agency_id`.

## Verification

Passed:

- `python -m compileall app`
- Route registration inspection for all `/api/v1/leads` endpoints
- DB-backed FastAPI smoke test covering:
  - temporary registered user, Agency Admin, and Agent creation
  - inquiry creation against an approved property
  - Agency Admin lead listing
  - Agency Admin assignment to Agent
  - Agent lead access
  - Agent note creation
  - Agent email-mode lead message with log-mode email
  - Agent close request
  - Agency Admin close approval
  - cleanup of temporary users, lead records, status history, notes, messages, notifications, and activity logs

## Remaining Development

Move to Phase 7 after this checkpoint. Expected next backend focus:

- Property deal-closure request workflow
- Agency Admin deal-closure approval/rejection
- Existing approved listing remains visible while edits are pending reapproval
- Deal-closed properties are removed from public search and no longer accept inquiries

