# DCO Implementation Tracker - 2026-06-29

## Scope

This tracker covers the DCO changes for property taxonomy, listing status visibility, agency registration/invitation workflows, login UI restructuring, and property creation API compatibility across:

- `abdoun_fast_api`
- `mls_website`
- `abdoun-library`

## Implemented Items

| Area | Status | Notes |
| --- | --- | --- |
| Property type tabs | Complete | Backend taxonomy, DB seed data, MLS filters, and shared UI now use Residential, Commercial, Land ordering. |
| Residential type order | Complete | Apartments, Villas, Buildings, Farms. |
| Commercial type order | Complete | Offices, Showrooms, Buildings, Warehouse, Businesses, Villas. |
| Land type order | Complete | Residential Lands, Commercial Lands, Industrial Lands, Agricultural Lands, Mixed Use Lands. |
| Property status normalization | Complete | Runtime workflow now uses `draft`, `pending-approval`, `active`, `rejected`, `deal-closure-requested`, `deal-closed`. Legacy `submitted` and `approved` data is migrated to `pending-approval` and `active`. |
| My Listings visibility | Complete | Default My Listings response is active-only. Draft Listings remains draft-only. |
| Draft privacy | Complete | Draft submissions are visible/editable only by the owner who created them. Admin/agent lists exclude drafts. |
| Active property revision | Complete | Active properties can be edited by permitted users through a reapproval revision while the active version remains visible. |
| Agency invitation model | Complete | `agency_invitations` stores invitation state separately from `agency_master`; `Invited` is not an agency status. |
| Agency statuses | Complete | Agency records use `PENDING_APPROVAL`, `APPROVED`, `REJECTED`, `ACTIVE`. |
| Invitation expiry | Complete | Invitation links expire after `AGENCY_INVITATION_TTL_SECONDS`, default 900 seconds. |
| Password setup expiry | Complete | Password setup links expire after `AGENCY_PASSWORD_SETUP_TTL_SECONDS`, default 900 seconds. |
| Dev email/SMS mode | Complete | Notification delivery continues through existing dev/log mode until real gateway details are provided. |
| Login UI restructuring | Complete | Login entry screen separates social login from email/OTP authentication without changing auth logic. |
| Unified property creation API | Compatible | Current `/property-submissions` API remains the unified create/update/submit surface for all categories; category-specific validation remains backend-owned. |

## Database Changes Applied

- Added `agency_master.status`.
- Added `agency_invitations`.
- Added `display_order` to `property_categories`, `property_types`, and `property_status`.
- Seeded/normalized DCO taxonomy and property status records.
- Migrated old listing statuses:
  - `submitted`, `pending`, `pending_admin_approval` -> `pending-approval`
  - `approved`, `verified`, `available` -> `active`
- Deactivated legacy status rows `approved`, `available`, `verified`, `pending`, `sold`, `rented`.

Current DB revision after migration: `0058_dco_status_cleanup`.

## Verification Completed

- Backend Python compile: passed.
- Backend route import check: passed.
- Alembic migration against configured test DB: passed through `0058_dco_status_cleanup`.
- DB taxonomy/status verification: passed.
- Shared library build: passed.
- MLS production build: passed.

## Remaining Business Notes

- Rejected property discoverability is still a product decision. Current DCO wording says My Listings is active-only and Draft Listings is draft-only, while BRD says rejected properties can be corrected/resubmitted. A separate "Action Required" or "Rejected Listings" view may be needed if business wants rejected listings easily discoverable without direct links.
- Agency registration frontend screens may still need UX refinement to fully expose every new Super Admin invitation/offline workflow endpoint. Backend workflow endpoints are available.
