# Phase 7 Completion Status - Deal Closure and Approved Property Revisions

Date: 2026-06-24

## Scope Completed

Phase 7 implements property deal-closure workflow and approved-property edit/reapproval behavior.

Implemented backend endpoints:

- `POST /api/v1/deal-closures`
- `GET /api/v1/deal-closures`
- `GET /api/v1/deal-closures/{closure_id}`
- `POST /api/v1/deal-closures/{closure_id}/review`

Updated backend behavior:

- `PATCH /api/v1/property-submissions/{submission_id}` now supports approved-property edits by creating a submitted revision.
- Public property list/detail now expose only the latest approved version for a property.
- Public property list/detail now exclude properties with approved deal closure.
- Lead creation uses the same public property resolver, so deal-closed properties no longer accept new inquiries.

## DB Change

Added Alembic revision:

- `0054_property_deal_closures`

Added table:

- `property_deal_closures`

Main columns:

- `id`
- `property_id`
- `lead_id`
- `agency_id`
- `requested_by`
- `status`
- `reason`
- `review_reason`
- `reviewed_by`
- `requested_at`
- `reviewed_at`
- `created_at`
- `updated_at`

Indexes:

- `ix_property_deal_closures_property_id`
- `ix_property_deal_closures_agency_status`
- `ix_property_deal_closures_status`

## Business Rules Implemented

- Approved properties can be edited without replacing the currently visible approved listing.
- Approved-property edits create a new `submitted` revision row with the same `property_id`.
- The existing approved version remains public while the revision is pending.
- When the revision is approved, public APIs show the latest approved version.
- Deal closure can be requested by the submitter, assigned agent, or agency admin.
- Agency Admin reviews deal-closure requests.
- Super Admin can view deal closures but is not used for agency operational approval.
- Approved deal closure removes the property from public search/detail.
- Approved deal closure prevents new inquiries because lead creation resolves only public active properties.
- Rejected deal closure returns the property workflow marker to active.
- Deal-closure request/review writes audit activity and in-app notifications.

## Verification

Passed:

- `python -m compileall app alembic`
- `python -m alembic upgrade head`
- `python -m alembic current`
- `python -m alembic heads`
- DB-backed FastAPI smoke test covering:
  - approved property public detail visible before edit
  - approved edit creates submitted revision
  - public detail remains on old approved version while revision is pending
  - revision approval makes latest approved version public
  - deal-closure request creation
  - Agency Admin deal-closure approval
  - approved deal-closed property returns `404` from public detail
  - approved deal-closed property is excluded from public list
  - cleanup of temporary revision, closure request, workflow markers, and temporary admin user

## Remaining Development

Move to Phase 8 after this checkpoint. Expected next backend focus:

- Notification polling/list endpoints and preferences
- Audit-log API exposure for admin views
- Document category/configuration APIs if needed by frontend

