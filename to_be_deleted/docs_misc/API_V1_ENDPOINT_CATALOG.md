# API v1 endpoint catalog

**Base URL:** `{API_V1_PREFIX}` from settings (default `/api/v1` per `SystemMessages.API_V1_PREFIX`).  
**Full path:** `{API_V1_PREFIX}` + **prefix** + **path** below.

This catalog maps each mounted router to its HTTP operations for quick cross-checks with OpenAPI (`/api/v1/docs` when `debug` is enabled). **Auth** summarizes typical dependencies on the handler; verify in code for edge cases.

---

## Router composition

Defined in `app/api/v1/router.py` using prefixes from `app/utils/constants.py` (`ApiRoutes`).

| Prefix constant | HTTP prefix | Tag(s) | Module |
|-----------------|------------|--------|--------|
| `AUTH_PREFIX` | `/auth` | auth | `routes/auth.py` |
| `AGENT_PREFIX` | `/agent` | agent | `routes/agent.py` |
| `AGENTS_PREFIX` | `/agents` | agents | `routes/agents.py` |
| `ADMIN_PREFIX` | `/admin` | admin | `routes/admin.py`, `routes/admin_properties.py` |
| `USERS_PREFIX` | `/users` | users | `routes/users.py`, `routes/recent_views.py` |
| `OWNERS_PREFIX` | `/owners` | owners | `routes/owners.py` |
| `FAVORITES_PREFIX` | `/favorites` | favorites | `routes/favorites.py` |
| `SAVED_SEARCHES_PREFIX` | `/saved-searches` | saved-searches | `routes/saved_searches.py` |
| `PROPERTY_SUBMISSIONS_PREFIX` | `/property-submissions` | property-submissions | `routes/property_submissions.py` |
| `ADMIN_PROPERTY_SUBMISSIONS_PREFIX` | `/admin/property-submissions` | admin-property-submissions | `routes/admin_property_submissions.py` |
| `UPLOADS_PREFIX` | `/uploads` | uploads | `routes/uploads.py` |
| `AGENT_PROPERTIES_PREFIX` | `/agent-properties` | agent-properties | `routes/agent_properties.py` |
| `PROPERTIES_PREFIX` | `/properties` | properties, search | `routes/properties.py`, `routes/search.py` |
| *(none)* | *(root of v1)* | locations | `routes/locations.py` — `/location-taxonomy` |
| *(none)* | *(root of v1)* | taxonomy | `routes/property_taxonomy.py` — `/property-taxonomy` |

---

## Endpoints by module

### `auth` — `/auth`

| Method | Path | Auth / limits | Delegates to |
|--------|------|---------------|--------------|
| POST | `/signup` | Rate limited | `AuthService.signup` |
| POST | `/signup/admin` | Admin role; returns 404 (deprecated) | — |
| POST | `/confirm-signup` | Public | `AuthService.confirm_signup` |
| POST | `/resend-confirmation` | Public | `AuthService.resend_confirmation` |
| POST | `/login/password` | Rate limited | `AuthService.login_password` |
| POST | `/login/otp/request` | Rate limited | `AuthService.login_otp_request` |
| POST | `/login/otp/verify` | Rate limited | `AuthService.login_otp_verify` |
| POST | `/refresh` | Public | `AuthService.refresh_token` |
| POST | `/logout` | Bearer | `AuthService.logout` |
| POST | `/forgot-password/request` | Rate limited | `AuthService.forgot_password_request` |
| POST | `/forgot-password/confirm` | Rate limited | `AuthService.forgot_password_confirm` |
| POST | `/set-password` | Bearer | `AuthService.set_password` |
| POST | `/change-password` | Bearer | `AuthService.set_password` |
| GET | `/social-login` | Public | `AuthService.social_login` |
| GET | `/me` | Bearer | `AuthService.get_current_user_profile` |
| POST | `/me/profile-picture` | Bearer | `ProfilePictureUploadService` + `MediaUrlSigner` |
| PATCH | `/me/profile/request` | Bearer, rate limited | `ProfileUpdateService.request_profile_update` |
| POST | `/me/profile/verify` | Bearer, rate limited | `ProfileUpdateService.verify_profile_update` |
| GET | `/me/permissions` | Bearer | `AuthService.get_current_user_permissions` |
| GET | `/callback` | Public (OAuth) | `AuthService.social_callback` |

**SOLID note:** Thin handlers; auth and profile concerns split across services — good **SRP** at handler level.

---

### `agent` (singular) — `/agent`

| Method | Path | Auth | Delegates to |
|--------|------|------|--------------|
| GET | `/property-performance` | `require_role(AGENT)` | `AdminDashboardService.get_property_performance` (scoped to current user) |

**SOLID note:** Reuses admin dashboard service for agent-scoped analytics — pragmatic **DIP** reuse; naming may confuse readers (**ISP** / clarity).

---

### `agents` — `/agents`

| Method | Path | Auth | Notes |
|--------|------|------|--------|
| POST | `/invite` | Admin | `AgentService.invite_agent` |
| POST | `/manual-onboard` | Admin | `AgentService.create_agent_direct` |
| GET | `` | Admin | List + pagination; query compat in handler |
| GET | `/summary` | Admin | |
| GET | `/leaderboard` | Admin | |
| GET | `/invites` | Admin | |
| GET | `/assignments` | Admin | |
| GET | `/dashboard/summary` | **Agent** | `AgentDashboardService` |
| GET | `/{agent_id}` | Admin | |
| PATCH | `/{agent_id}/accept` | Admin | |
| PATCH | `/{agent_id}/decline` | Admin | |
| PATCH | `/{agent_id}/status` | Admin | |
| DELETE | `/{agent_id}` | Admin | |
| POST | `/{agent_id}/resend-invite` | Admin | |
| POST | `/{agent_id}/resend-invitation` | Admin | Alias |
| PATCH | `/{agent_id}/revoke-invite` | Admin | |
| GET | `/invite/validate` | Public | `include_in_schema=False` |
| POST | `/onboarding` | Public | Compat; validation/normalization in handler |
| POST | `/assign-agent` | Admin | |
| POST | `/unassign-agent` | Admin | |

**SOLID note:** Large surface area in one module — **SRP** at file level is strained; compat paths add **OCP** maintenance cost.

---

### `admin` — `/admin`

| Method | Path | Auth | Delegates to |
|--------|------|------|--------------|
| GET | `/dashboard/kpis` | Admin | `AdminDashboardService.get_kpis` |
| GET | `/dashboard/trends` | Admin | `AdminDashboardService.get_trends` |
| GET | `/property-performance` | Admin | `AdminDashboardService.get_property_performance` + pagination in handler |
| GET | `/dashboard/summary` | Admin | `AdminDashboardService.get_dashboard_summary` |
| GET | `/dashboard/recent-activity` | Admin | `AdminDashboardService.get_recent_activity` |
| GET | `/recent-activity` | Admin | Alias |

**SOLID note:** Pagination DTO assembly duplicated with `agent` router — **DRY/SRP** opportunity.

---

### `admin_properties` — `/admin`

| Method | Path | Auth | Delegates to |
|--------|------|------|--------------|
| PATCH | `/properties/{property_id}/assign-agent` | Admin | `PropertyAdminService.assign_agent_to_property` |

---

### `users` — `/users`

| Method | Path | Auth | Delegates to |
|--------|------|------|--------------|
| GET | `` | Permission `USER_CREATE` | `UserService.list_users` + `MediaUrlSigner` |
| GET | `/roles/list` | Permission `ROLE_ASSIGN` | `UserService.list_roles` |
| GET | `/permissions/list` | Permission `ROLE_ASSIGN` | `UserService.list_permissions` |
| GET | `/{id}` | Permission `USER_CREATE` | `UserService.get_user` |
| PATCH | `/{id}` | Permission `USER_CREATE` | `UserService.update_user` |
| DELETE | `/{id}` | Permission `USER_DELETE` | `UserService.delete_user` |
| POST | `/{id}/roles` | Permission `ROLE_ASSIGN` | `UserService.assign_role` |
| DELETE | `/{id}/roles/{role_id}` | Permission `ROLE_ASSIGN` | `UserService.remove_role` |

---

### `recent_views` — `/users`

| Method | Path | Auth | Delegates to |
|--------|------|------|--------------|
| POST | `/recent-views` | Bearer | `RecentViewService` |
| GET | `/recent-views` | Bearer | |
| DELETE | `/recent-views` | Bearer | |
| DELETE | `/recent-views/{property_hash}` | Bearer | |

---

### `owners` — `/owners`

| Method | Path | Auth | Delegates to |
|--------|------|------|--------------|
| POST | `` | **None on router** | `OwnerService.create_owner` |
| GET | `` | **None** | `OwnerService.list_owners` |
| GET | `/{owner_id}` | **None** | `OwnerService.get_owner` |
| PATCH | `/{owner_id}` | **None** | `OwnerService.update_owner` |
| DELETE | `/{owner_id}` | **None** | `OwnerService.delete_owner` |
| POST | `/property-mappings` | **None** | `OwnerService.create_property_owner_mapping` |
| PATCH | `/property-mappings/{mapping_id}` | **None** | `OwnerService.update_property_owner_mapping` |
| DELETE | `/property-mappings/{mapping_id}` | **None** | `OwnerService.delete_property_owner_mapping` |

**SOLID / security note:** Missing auth at the API boundary breaks **segregation of concerns** between public API and internal data management; treat as high priority if exposed.

---

### `favorites` — `/favorites`

| Method | Path | Auth | Delegates to |
|--------|------|------|--------------|
| POST | `` | Bearer | `FavoriteService.add_favorite` |
| POST | `/bulk` | Bearer | `FavoriteService.add_favorites_bulk` |
| GET | `` | Bearer | `FavoriteService.list_favorites` |
| DELETE | `/{property_hash}` | Bearer | `FavoriteService.remove_favorite` |

---

### `saved_searches` — `/saved-searches`

| Method | Path | Auth | Delegates to |
|--------|------|------|--------------|
| POST | `` | Bearer | `SavedSearchService.create_saved_search` |
| POST | `/bulk` | Bearer | `SavedSearchService.create_saved_searches_bulk` |
| GET | `` | Bearer | `SavedSearchService.list_saved_searches` |
| GET | `/{id}` | Bearer | `SavedSearchService.get_saved_search` |
| DELETE | `/{id}` | Bearer | `SavedSearchService.delete_saved_search` |
| PATCH | `/{id}` | Bearer | `SavedSearchService.update_saved_search` |
| GET | `/{id}/results` | Bearer | `SavedSearchService.execute_saved_search` |

---

### `property_submissions` — `/property-submissions`

| Method | Path | Auth | Delegates to |
|--------|------|------|--------------|
| POST | `` | Bearer | `PropertySubmissionService.create_submission` |
| POST | `/submit` | Bearer | `PropertySubmissionService.create_and_submit_submission` |
| GET | `/{submission_id}` | Bearer | `PropertySubmissionService.get_submission` |
| PATCH | `/{submission_id}` | Bearer | `PropertySubmissionService.patch_submission` |
| POST | `/{submission_id}/submit` | Bearer | `PropertySubmissionService.submit_submission` |
| DELETE | `/{submission_id}` | Bearer | `PropertySubmissionService.delete_submission_with_reason` |

---

### `admin_property_submissions` — `/admin/property-submissions`

| Method | Path | Auth | Delegates to |
|--------|------|------|--------------|
| GET | `` | Admin | `PropertySubmissionService.list_admin_submissions` |
| GET | `/drafts` | Admin | Draft list (adapter mapping in handler) |
| GET | `/{submission_id}` | Admin | `PropertySubmissionService.get_admin_submission` |
| POST | `/{submission_id}/review` | Admin | `PropertySubmissionService.review_submission` |
| POST | `/submit` | Admin | `PropertySubmissionService.admin_create_and_approve_submission` |
| POST | `/{submission_id}/submit` | Admin | `PropertySubmissionService.admin_submit_existing_draft_and_approve` |
| DELETE | `/{submission_id}` | Admin | `PropertySubmissionService.admin_soft_delete_submission` |

---

### `uploads` — `/uploads`

| Method | Path | Auth | Delegates to |
|--------|------|------|--------------|
| POST | `/presigned-url` | Bearer | `UploadService.generate_presigned_upload` |

---

### `agent_properties` — `/agent-properties`

| Method | Path | Auth | Delegates to |
|--------|------|------|--------------|
| GET | `` | Bearer | `AgentPropertyService.list_my_properties` |
| GET | `/drafts` | Bearer | `AgentPropertyService.list_my_draft_submissions` |

---

### `properties` + `search` — `/properties`

| Method | Path | Auth | Response style |
|--------|------|------|----------------|
| GET | `` | Optional user (not required) | `PropertySearchService.search` → `PropertySearchResponse` |
| GET | `/exclusive` | Optional | Same |
| GET | `/{property_id}/similar` | Optional | Same |
| GET | `/{property_id}` | Optional; tracking if logged in | `PropertyDetail` + side effect via `RecentViewService` |
| POST | `/geo-search` | Public | `GeoSearchService.search` → `PropertyListResponse` |
| POST | `/import-csv` | Permission `PROPERTY_CREATE` | `PropertyImportService.import_from_csv` → `ImportResponse` |

**SOLID note:** Mixed envelope types (`StandardResponse` vs plain schemas); detail handler mixes **read + write** (recent view).

---

### `locations` — v1 root

| Method | Path | Auth | Returns |
|--------|------|------|---------|
| GET | `/location-taxonomy` | Public | `dict` from `LocationService.get_location_taxonomy` |

**SOLID note:** Prefer a Pydantic response model for contract stability (**DIP** at API boundary).

---

### `property_taxonomy` — v1 root

| Method | Path | Auth | Returns |
|--------|------|------|---------|
| GET | `/property-taxonomy` | Public | `dict` from `PropertyTaxonomyService.get_property_taxonomy` |

---

## App-level (not under `api_router` prefix)

| Method | Path | Source | Purpose |
|--------|------|--------|---------|
| GET | `/health` | `app/main.py` | Health check |
| GET | `/metrics` | `app/main.py` (if enabled) | Prometheus |

---

## Document index

- **SOLID-focused analysis:** `docs/API_SOLID_ARCHITECTURE_REVIEW.md`
- **Broader audit:** `FINAL_FASTAPI_BACKEND_AUDIT.md`, `FASTAPI_BACKEND_AUDIT_VALIDATION.md`
