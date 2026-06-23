# Frontend and Backend Contract Inventory

Date: 2026-06-23  
Branch: `feature/autonomous-remaining-development`  
Scope: Phase 0 discovery for autonomous remaining development

## Purpose

This inventory records the API surface currently expected by the MLS website and compares it with the API surface currently implemented by the backend.

It is intentionally limited to source-code evidence. The live DB schema still cannot be inspected because the configured database credentials are rejected by the server.

## Backend API Currently Implemented

The backend currently exposes a narrow FastAPI surface:

| Method | Path | Source | Notes |
| --- | --- | --- | --- |
| GET | `/health` | `app/main.py` | Application health check |
| GET | `/api/v1/properties` | `app/api/v1/routes/properties.py` | Basic list with `limit` and `offset` |
| GET | `/api/v1/properties/{property_id}` | `app/api/v1/routes/properties.py` | Basic property detail by integer ID |
| POST | `/api/v1/search` | `app/api/v1/routes/search.py` | Spatial search by bounds or polygon |
| POST | `/api/v1/import-csv` | `app/api/v1/routes/search.py` | CSV import for property data |

Current implemented model coverage:

| Model | Table | Source | Notes |
| --- | --- | --- | --- |
| `Property` | `properties` | `app/models/property.py` | Basic listing/search fields only |

Current migration coverage:

| Revision | Purpose |
| --- | --- |
| `0001_create_properties.py` | Create initial `properties` table |
| `0002_add_integer_id.py` | Add integer ID support |
| `0003_add_location_name.py` | Add `location_name` |

## MLS Website API Contract Currently Expected

The MLS website has centralized endpoint definitions under `mls_website/src/apis/endpoints`.

### Auth and Profile

| Method Needed | Path Expected | Frontend Source | Backend Status |
| --- | --- | --- | --- |
| POST | `/auth/login/password` | `authEndpoints.ts` | Missing |
| POST | `/auth/login/otp/request` | `authEndpoints.ts` | Missing |
| POST | `/auth/login/otp/verify` | `authEndpoints.ts` | Missing |
| GET | `/auth/me` | `authEndpoints.ts`, `profileEndpoints.ts` | Missing |
| PATCH/PUT | `/auth/me` | `profileEndpoints.ts` | Missing |
| POST | `/auth/forgot-password/request` | `authEndpoints.ts` | Missing |
| POST | `/auth/forgot-password/confirm` | `authEndpoints.ts` | Missing |
| POST | `/auth/change-password` | `authEndpoints.ts` | Missing |
| POST | `/auth/refresh` | `authEndpoints.ts` | Missing |
| POST | `/auth/logout` | `authEndpoints.ts` | Missing |
| POST | `/auth/signup` | `authEndpoints.ts` | Missing |
| POST | `/auth/confirm-signup` | `authEndpoints.ts` | Missing |
| POST | `/auth/me/profile/request` | `profileEndpoints.ts` | Missing |
| POST | `/auth/me/profile/verify` | `profileEndpoints.ts` | Missing |
| POST/DELETE | `/auth/me/profile-picture` | `profileEndpoints.ts` | Missing |

Implementation implication:

- Phase 2 must add auth, user identity, roles, tokens, OTP/dev-mode email/SMS logging, profile update verification, and role-aware current-user payloads.

### Agency

| Method Needed | Path Expected | Frontend Source | Backend Status |
| --- | --- | --- | --- |
| POST | `/agency/register` | `authEndpoints.ts` | Missing |
| GET | `/agency/list?skip=&limit=` | `agencyEndpoints.ts` | Missing |
| GET/PATCH | `/agency/{agencyId}` | `agencyEndpoints.ts` | Missing |
| POST/DELETE | `/agency/{agencyId}/logo` | `agencyEndpoints.ts` | Missing |
| POST | `/agency/{agencyId}/legal-document` | `agencyEndpoints.ts` | Missing |
| POST/PUT | `/users/agency` | `userEndpoints.ts` | Missing |

Implementation implication:

- Phase 2 must add agency registration, onboarding status, agency activation, agency document upload metadata, logo handling, and tenant scoping by `agency_id`.
- Super Admin owns agency onboarding and activation.
- Agency Admin owns agency operations after activation.

### Agents

| Method Needed | Path Expected | Frontend Source | Backend Status |
| --- | --- | --- | --- |
| GET | `/agents?page=&pageSize=&sortBy=&sortOrder=` | `agentEndpoints.ts` | Missing |

Implementation implication:

- Phase 3 must add agent list, agency-scoped filtering, invitation/onboarding support, status handling, and Agency Admin management actions.

### Public Taxonomy

| Method Needed | Path Expected | Frontend Source | Backend Status |
| --- | --- | --- | --- |
| GET | `/property-taxonomy` | `publicEndpoints.ts` | Missing |
| GET | `/location-taxonomy` | `publicEndpoints.ts` | Missing |
| GET | `/features?is_active=true` | `propertyEndpoints.ts` | Missing |

Implementation implication:

- Phase 5 or earlier backend foundation must add configurable property categories, property types, features/amenities, and location taxonomy APIs.
- These APIs should support multilingual labels for `en`, `ar`, `fr`, and `es`, with English fallback.

### Public Property Search and Details

| Method Needed | Path Expected | Frontend Source | Backend Status |
| --- | --- | --- | --- |
| GET | `/properties?page=&pageSize=&category=&status=...` | `propertyEndpoints.ts` | Partially mismatched |
| GET | `/properties/{id}` | `propertyEndpoints.ts` | Partially available |
| GET | `/properties/{id}/similar` | `propertyEndpoints.ts` | Missing |

Current mismatch:

- Backend list uses `limit` and `offset`; frontend expects `page` and `pageSize`.
- Frontend expects many filters not currently supported by backend list.
- Backend currently returns a basic property shape; frontend feature modules expect richer listing/detail payloads.
- Only `Active` properties should appear in public search for MVP.

Implementation implication:

- Phase 4 and Phase 5 must align property schemas, lifecycle status filtering, media/documents, localization, search filters, and similar-property support.

### Agent and Admin Property Workflows

| Method Needed | Path Expected | Frontend Source | Backend Status |
| --- | --- | --- | --- |
| GET | `/agent-properties?...` | `propertyEndpoints.ts` | Missing |
| GET | `/agent-properties/drafts?...` | `propertyEndpoints.ts` | Missing |
| GET | `/admin/property-submissions?...` | `propertyEndpoints.ts` | Missing |
| POST/PATCH | `/admin/property-submissions/{submissionId}/review` | `propertyEndpoints.ts` | Missing |
| POST/PATCH | `/admin/properties/{propertyId}/assign-agent` | `propertyEndpoints.ts` | Missing |
| POST | `/property-submissions` | `propertyEndpoints.ts` | Missing |
| POST | `/property-submissions/submit` | `propertyEndpoints.ts` | Missing |
| GET/PATCH/DELETE | `/property-submissions/{submissionId}` | `propertyEndpoints.ts` | Missing |
| POST | `/property-submissions/{submissionId}/submit` | `propertyEndpoints.ts` | Missing |

Implementation implication:

- Phase 4 must add property drafts, submissions, approval/rejection, assignment, audit logging, and notification triggers.
- Approved property edits must create a pending revision while the existing approved version remains visible.
- Super Admin approves/rejects property submissions.
- Property Owner, Assigned Agent, and Agency Admin may edit approved properties, but edits require reapproval.

### Favorites and Recent Views

| Method Needed | Path Expected | Frontend Source | Backend Status |
| --- | --- | --- | --- |
| GET/POST | `/favorites` | `propertyEndpoints.ts` | Missing |
| GET | `/favorites?page=&pageSize=` | `propertyEndpoints.ts` | Missing |
| DELETE | `/favorites/{propertyHash}` | `propertyEndpoints.ts` | Missing |
| GET/POST/DELETE | `/users/recent-views` | `userEndpoints.ts` | Missing |
| GET | `/users/recent-views?page=&pageSize=` | `userEndpoints.ts` | Missing |
| DELETE | `/users/recent-views/{propertyId}` | `userEndpoints.ts` | Missing |

Implementation implication:

- Phase 5 must add user-property preference tables and APIs for favorites and recent views.

### Saved Searches

| Method Needed | Path Expected | Frontend Source | Backend Status |
| --- | --- | --- | --- |
| POST | `/saved-searches` | `savedSearchEndpoints.ts` | Missing |
| GET | `/saved-searches?page=&pageSize=` | `savedSearchEndpoints.ts` | Missing |
| GET/PATCH/DELETE | `/saved-searches/{id}` | `savedSearchEndpoints.ts` | Missing |

Implementation implication:

- Phase 5 must add saved-search CRUD.
- MVP excludes saved-search notification matching.

### Uploads and Documents

| Method Needed | Path Expected | Frontend Source | Backend Status |
| --- | --- | --- | --- |
| POST | `/uploads/presigned-url` | `uploadEndpoints.ts` | Missing |
| POST | `/agency/{agencyId}/legal-document` | `agencyEndpoints.ts` | Missing |
| Property document upload paths | Property form/shared library | Missing |

Implementation implication:

- Phase 4 must support configurable document categories and approval states.
- Exact business document type lists remain configurable because final lists are not confirmed in the BRD.
- If object storage details are unavailable, implement a storage-provider abstraction with local/dev behavior where appropriate.

### Notifications

| Method Needed | Path Expected | Frontend Source | Backend Status |
| --- | --- | --- | --- |
| GET | `/notifications?page=&pageSize=&includeArchived=` | `notificationEndpoints.ts` | Missing |
| GET | `/notifications/unread-count` | `notificationEndpoints.ts` | Missing |
| PATCH/POST | `/notifications/{id}/read` | `notificationEndpoints.ts` | Missing |
| PATCH/POST | `/notifications/read-all` | `notificationEndpoints.ts` | Missing |
| PATCH/POST | `/notifications/{id}/archive` | `notificationEndpoints.ts` | Missing |
| PATCH/POST | `/notifications/{id}/unarchive` | `notificationEndpoints.ts` | Missing |
| DELETE | `/notifications/{id}` | `notificationEndpoints.ts` | Missing |

Implementation implication:

- Phase 8 must add in-app notification storage and polling APIs.
- Default polling interval is 30 seconds while the app is active and should be configurable.
- Email and SMS notifications must use provider abstraction with log-only mode until gateway details are supplied.

### Lead and Deal Closure APIs

No current frontend endpoint module was found for lead management or deal closure.

Implementation implication:

- Phase 6 must add lead management APIs before frontend integration.
- Phase 7 must add deal closure request/review APIs before frontend integration.
- MLS frontend endpoint modules and screens will need to be added or extended in later phases.

## Role and Scope Rules to Preserve

| Area | Rule |
| --- | --- |
| Tenant scoping | Agency-specific data must be scoped by `agency_id`; Super Admin can see across agencies |
| Agency Admin | Handles agency operations and deal closure approvals within agency |
| Super Admin | Handles platform-wide agency onboarding and property submission approval |
| Property visibility | Only `Active` properties appear in public search |
| Approved property edits | Pending revision goes to reapproval; current approved version remains visible |
| Deal closure | Agency Admin approval moves property to `Deal Closed`; property is removed from public search and inquiries |
| Notifications | In-app polling in MVP; email/SMS logged in dev mode until gateways are configured |
| Localization | Support `en`, `ar`, `fr`, `es`; Arabic is RTL; English fallback |

## Phase 0 Conclusion

The MLS frontend already anticipates most of the target product surface, but the backend currently implements only the property import/search seed service.

Phase 1 backend implementation should not begin until the live demo DB schema is inspected, because the final migration strategy depends on the current database state. Once DB authentication is corrected, rerun:

```powershell
python scripts\inspect_db_schema.py --markdown docs\phase0\Live_DB_Schema_Inventory.md --json docs\phase0\live_db_schema_inventory.json
```

After that, produce the final DB/API implementation spec for Phase 1 and continue development.
