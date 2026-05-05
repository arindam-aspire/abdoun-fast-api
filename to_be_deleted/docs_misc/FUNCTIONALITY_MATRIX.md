# Functionality Matrix (Current Implementation)

This matrix summarizes **what exists today** and where it lives in code.

## 1) API capabilities by domain

| Domain | Core capabilities | Primary route modules | Core services |
|---|---|---|---|
| Auth & profile | signup/login/password/OTP/refresh/logout, profile update verification, permissions | `auth.py` | `AuthService`, `ProfileUpdateService`, `ProfilePictureUploadService` |
| Users & RBAC | list/update/delete users, assign/remove roles, list roles/permissions | `users.py` | `UserService` |
| Agents | invite/onboard/list/update status/assignment flows, leaderboard/summary | `agents.py`, `agent.py` | `AgentService`, `AgentDashboardService`, `AdminDashboardService` |
| Admin dashboard | KPIs, trends, property performance, recent activity | `admin.py` | `AdminDashboardService` |
| Properties | list/filter/exclusive/detail/similar | `properties.py` | `PropertySearchService` |
| Geo search/import | geospatial search, CSV import endpoint | `search.py` | `GeoSearchService`, `PropertyImportService` |
| Taxonomy | location taxonomy, property taxonomy | `locations.py`, `property_taxonomy.py` | `LocationService`, `PropertyTaxonomyService` |
| Submissions | agent draft/submit lifecycle, admin moderation and force-submit paths | `property_submissions.py`, `admin_property_submissions.py` | `PropertySubmissionService` |
| Agent property list | paginated property and draft views for current agent | `agent_properties.py` | `AgentPropertyService` |
| Favorites | add/list/remove + bulk add | `favorites.py` | `FavoriteService` |
| Saved searches | CRUD + execute saved search | `saved_searches.py` | `SavedSearchService` |
| Recent views | add/list/remove/clear recent property views | `recent_views.py` | `RecentViewService` |
| Uploads | presigned URL workflow for file uploads | `uploads.py` | `UploadService` |
| Owners | owner + property-owner mapping CRUD | `owners.py` | `OwnerService` |
| Admin property assignment | assign/unassign agent to property | `admin_properties.py` | `PropertyAdminService` |

## 2) Non-API functionality

### Observability and reliability

- Request IDs via middleware
- Security headers middleware
- Optional Prometheus metrics endpoint and middleware
- Optional OpenTelemetry instrumentation
- Optional Sentry integration
- Slow query tooling and observability helpers

### Scheduled work

- Dashboard summary scheduler, startup-controlled by config

### Media/storage

- S3 service utilities
- media URL signer for client-facing URLs
- upload constraints configured from env

## 3) Data and migration workflows

### Data lifecycle scripts (`scripts/`)

- reference data seeding
- RBAC seeding and verification
- normalized CSV import
- geo-enrichment of CSV
- translation/backfill scripts
- pricing/features/reference-number/exclusive update scripts
- endpoint/auth/admin-assignment test scripts
- pipeline and sync utilities

### DB evolution

- Alembic migration history under `alembic/versions`
- model/repository/service layers aligned with migration-driven schema updates

## 4) Testing coverage shape

| Area | Coverage type | Examples |
|---|---|---|
| Services | Unit tests | agent, auth, submissions, dashboard, upload, search |
| Repositories | Unit tests | admin dashboard, taxonomy, location, agent repository |
| API routes/deps | Unit tests | auth routes, agents routes, deps injection |
| Architecture guards | Validation tests | no direct DB access in routers |
| Contracts/security | API contract & security tests | route contracts, security controls, route coverage |

## 5) Current architecture posture (practical)

- Strongly service-oriented route handlers in most domains.
- Repositories exist for key persistence-heavy domains.
- Dependencies are mostly composed via `Depends` providers.
- Configuration and feature toggles are env-driven and centralized.

## 6) Recommended usage of this matrix

- Use this file for feature ownership lookup and refactor impact analysis.
- Use `docs/API_V1_ENDPOINT_CATALOG.md` for endpoint-level details.
- Use `docs/CODEBASE_CURRENT_STATE.md` for system-level onboarding context.
- Keep this file updated when adding/removing route modules or core services.

