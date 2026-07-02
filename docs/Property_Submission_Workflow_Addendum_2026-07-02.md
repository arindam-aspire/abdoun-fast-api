# Property Submission Workflow Addendum

Status: Implemented in `feature/autonomous-remaining-development`; ready for BA / Technical Head validation

Date: 2026-07-02

## Decisions

- Keep the public status/API value as `Pending Approval` / `pending-approval`.
- Do not rename the label to `Pending Admin Approval`.
- Treat `Pending Approval` as a broad submitted state and use internal workflow custody to decide the current actor.
- `Deactivated` is an official property status.
- Do not introduce `Sold` or `Rented` as property statuses; they remain deal outcomes.
- Active properties are read-only for this workflow.

## Implemented Workflow Metadata

Workflow data is stored in `property_listing_submissions.payload._workflow`.

| Field | Purpose |
|---|---|
| `submission_origin` | `owner`, `agency_admin`, `agent`, or `super_admin`. |
| `workflow_stage` | Current custody stage. |
| `current_actor` | `owner`, `assigned_agent`, or `agency_admin`. |
| `assigned_agent_id` | Agent responsible for current or assigned review. |
| `last_actor_user_id` | User who performed the latest transition. |
| `last_transition_at` | Timestamp of the latest transition. |

Workflow stages:

| Stage | Meaning |
|---|---|
| `awaiting_agency_assignment` | Agency Admin must assign an agent before final approval review. |
| `with_agent` | Assigned Agent can view/edit/resubmit; Agency Admin is view-only. |
| `awaiting_agency_review` | Agency Admin can approve/reject agency property only. |
| `returned_to_owner` | Owner can view rejection reason, edit, and resubmit. |
| `returned_to_agent` | Assigned Agent can view rejection reason, edit, and resubmit. |
| `approved` | Approved listing is active/read-only. |

## Role Flows

Owner-origin submission:

1. Owner submits property.
2. Status becomes `pending-approval`, stage becomes `awaiting_agency_assignment`.
3. Agency Admin assigns an agent.
4. Stage becomes `with_agent`.
5. Assigned Agent edits/reviews and resubmits.
6. Stage becomes `awaiting_agency_review`.
7. Agency Admin approves or rejects.
8. Approval sets status `active`; rejection sets status `rejected` and stage `returned_to_owner`.

Agency Admin-origin submission:

1. Agency Admin submits property.
2. Status becomes `pending-approval`, stage becomes `awaiting_agency_assignment`.
3. Agency Admin assigns an agent.
4. Stage becomes `with_agent`.
5. Assigned Agent edits/reviews and resubmits.
6. Stage becomes `awaiting_agency_review`.
7. Agency Admin approves or rejects.
8. Approval sets status `active`; rejection sets status `rejected` and stage `returned_to_agent`.

Agent-origin submission:

1. Agent submits property.
2. Status becomes `pending-approval`, stage becomes `awaiting_agency_review`.
3. Agency Admin approves or rejects.
4. Approval sets status `active`; rejection sets status `rejected` and stage `returned_to_agent`.

## Permission Matrix

| Status | Stage | Owner | Assigned Agent | Agency Admin | Super Admin |
|---|---|---|---|---|---|
| Draft | n/a | Create/edit/delete own draft | Create/edit/delete own draft | Create/edit/delete own draft for agency-created property | View where allowed |
| Pending Approval | `awaiting_agency_assignment` | View own submission | No action unless assigned | View, assign agent | View |
| Pending Approval | `with_agent` | View own submission | View, edit, resubmit | View only | View |
| Pending Approval | `awaiting_agency_review` | View own submission | View assigned submission | View, approve, reject agency property only | View |
| Rejected | `returned_to_owner` | View reason, edit, resubmit | View if assigned | View only | View |
| Rejected | `returned_to_agent` | View if owner-created | View reason, edit, resubmit | View only | View |
| Active | `approved` | View only | View assigned property only | View/manage active assignment where allowed | View/deactivate per platform rules |
| Deactivated | n/a | View/history only | View/history only | View/history only | View/history only |
| Deal Closed | n/a | View/history only | View/history/reporting only | View/history/reporting only | View/history/reporting only |

## Implemented API Behavior

| API Area | Behavior |
|---|---|
| Submit | Sets `submission_origin`, `workflow_stage`, `current_actor`, and `assigned_agent_id` where applicable. |
| Assignment | Agency Admin can assign a pending submission while it is awaiting agency assignment. |
| Assignment route | Existing admin assignment route accepts either approved `property_id` or pending `submission_id`. |
| Update | Allows edit only for the current custody actor. |
| Review | Agency Admin can approve/reject only when stage is `awaiting_agency_review`. |
| Reject | Requires reason and routes custody back to owner or assigned agent based on origin. |
| List/detail | Returns `workflow_stage`, `current_actor`, `submission_origin`, `assigned_agent_id`, and action flags. |
| Notifications | Custody handoff notifications are sent to Agency Admins or Assigned Agent as appropriate. |

## Verification

- Backend compile: `python -m compileall app`
- Frontend build: `npm.cmd run build`
- Backend CORS preflight passes for `Origin: http://192.168.68.129:3000`
- API flows verified:
  - Owner submit -> agency assign -> agent resubmit -> agency approve.
  - Owner submit -> agency assign -> agent resubmit -> agency reject -> owner receives returned custody.
  - Agency Admin submit -> assign agent -> agent resubmit -> agency reject -> assigned agent receives returned custody.
  - Agent submit -> agency approve.

Browser note:

- The app is reachable at `http://192.168.68.129:3000/en`.
- API docs are reachable at `http://192.168.68.129:8001/docs`.
- In-app browser automation currently renders the page but does not trigger client click handlers; manual QA should validate the browser UI in Chrome/Edge while that tooling limitation is isolated.
