# Social Login Implementation Change Report

**Date:** 2026-05-04  
**Scope:** Production-ready social login hardening for Google/Facebook using AWS Cognito + PostgreSQL, while preserving existing JWT validation/RBAC architecture.

## Objective Completed

Implemented secure, maintainable social login with explicit social identity tracking and safe account linking rules, without changing the existing stateless auth model (Cognito-issued tokens only).

## Files Added

- `app/models/social_account.py`
  - New SQLAlchemy model `SocialAccount` for federated identity mapping.
  - Fields:
    - `id` (UUID, PK)
    - `user_id` (FK -> `users.id`, cascade delete)
    - `provider` (`google`/`facebook` canonical key)
    - `provider_user_id`
    - `created_at`
  - Constraints:
    - Unique: `(provider, provider_user_id)`
    - Index: `user_id`

- `alembic/versions/0039_create_social_accounts_table.py`
  - Migration to create `social_accounts` table.
  - `down_revision = "0038_backfill_agent"`.
  - Creates unique constraint and `user_id` index.

## Files Updated

### 1) Model and metadata wiring

- `app/models/user.py`
  - Added relationship:
    - `social_accounts` (`User` <-> `SocialAccount`, `all, delete-orphan`)
  - Imported `SocialAccount` model.

- `app/db/base.py`
  - Added import of `app.models.social_account` so Alembic/metadata loads the table.

### 2) Repository layer (`app/repositories/auth_repository.py`)

Added/updated methods to support clean identity resolution and linking:

- Added:
  - `get_user_by_cognito_sub(cognito_sub)`
  - `get_user_by_cognito_sub_including_deleted(cognito_sub)`
  - `get_social_account(provider, provider_user_id)`
  - `create_social_account(user_id, provider, provider_user_id)`
- Existing retained:
  - `get_user_by_email(email)` (already present)
- Updated:
  - `create_user(...)` now accepts `phone_number: Optional[str] = None`
    - Enables social-created users without placeholder phone values.

### 3) Constants and validation messages (`app/utils/constants.py`)

- Added social auth constants class:
  - `SocialAuth.PROVIDER_GOOGLE = "google"`
  - `SocialAuth.PROVIDER_FACEBOOK = "facebook"`
  - `SocialAuth.COGNITO_IDP_GOOGLE = "Google"`
  - `SocialAuth.COGNITO_IDP_FACEBOOK = "Facebook"`
- Updated default provider:
  - `Defaults.DEFAULT_SOCIAL_PROVIDER = "google"`
- Added API doc text:
  - `ApiDocs.SOCIAL_LOGIN_PROVIDER`
- Added new error messages:
  - `SOCIAL_MISSING_IDENTITIES`
  - `SOCIAL_UNSUPPORTED_PROVIDER`
  - `SOCIAL_EMAIL_REQUIRED_FOR_NEW_ACCOUNT`
  - `SOCIAL_EMAIL_ACCOUNT_CONFLICT`
  - `SOCIAL_IDENTITY_CONFLICT`

### 4) Auth service social flow rewrite (`app/services/auth_service.py`)

Implemented secure provider-aware social callback processing.

#### New helper types/functions

- `SocialTokenClaims` (`NamedTuple`) for strongly-typed extracted claims.
- Provider/claim helpers:
  - `_normalize_social_query_provider(...)`
  - `_canonical_provider_for_id_token(...)`
  - `_coerce_email_verified(...)`
  - `_identities_from_payload(...)`

#### Replaced social identity extraction

Old behavior:
- Relied on email/sub extraction only.
- Could resolve users via broad `cognito_sub OR email` fallback without provider mapping.

New behavior:
- `_parse_social_id_token_claims(...)` now enforces:
  - Valid ID token decode
  - Presence of `sub`
  - Presence of `identities[0]`
  - Supported provider only (`google`/`facebook`)
  - Extracted `provider_user_id` from `identities[0].userId`

#### Safe social user resolution order

Implemented in `_resolve_user_for_social_login(...)`:

1. Find by `cognito_sub` (including deleted for guard checks)
2. Find by `(provider, provider_user_id)` in `social_accounts`
3. If `email` exists AND `email_verified=True`, find by email
4. Else return `None` (caller creates new user)

#### Safe linking and creation

- `_link_social_account(...)`
  - Creates mapping if missing.
  - Rejects cross-user identity conflict (`409`).

- `_create_new_social_user(...)`
  - Requires email for new account creation.
  - Sets:
    - `cognito_sub`
    - `is_email_verified` from token claim
    - `is_active=True`
    - default `registered_user` role
  - Creates corresponding `social_accounts` row.

- `_finalize_social_session(...)`
  - Ensures local user alignment on social login:
    - set `cognito_sub` when absent
    - sync verification flags
    - ensure social mapping exists

- `social_callback(...)`
  - Replaced old callback logic with the new flow.
  - Returns unchanged token payload contract:
    - `access_token`, `refresh_token`, `id_token`, `expires_in`
  - No app-side token generation/session storage introduced.

- `social_login(...)`
  - Now validates provider (`google`/`facebook`) and maps to Cognito Hosted UI values (`Google`/`Facebook`) before generating URL.

### 5) Routes (`app/api/v1/routes/auth.py`)

- Updated `/social-login` endpoint parameter handling:
  - `provider` documented via `Query(..., description=ApiDocs.SOCIAL_LOGIN_PROVIDER)`
  - default provider now `google`
  - endpoint description updated for Google/Facebook support

### 6) Tests

- `tests/unit/services/test_auth_service_login_guards.py`
  - Updated social callback tests to include `identities` claim where needed.
  - Added/updated validations:
    - missing identities -> 400
    - unsupported provider -> 400
    - invalid social-login provider -> 400
    - inactive/soft-deleted user guard paths still enforced under new lookup method

### 7) Documentation updated

- `docs/AUTHENTICATION_SYSTEM_REPORT.md`
  - Updated social login section to reflect:
    - provider query options
    - `social_accounts` storage
    - secure resolution order
    - verified-email-only linking rule

## Security and Architecture Guarantees Preserved

The following were intentionally **not modified**:

- `get_current_user` dependency behavior
- JWT verification mechanism (JWKS/RS256/Cognito issuer/audience)
- RBAC (`require_role`, `require_permission`, permission inheritance)
- Middleware stack
- Stateless auth design (Cognito remains token authority)

## Behavior Changes (Practical)

- Social login now always records provider identity mapping.
- Email is no longer used as a primary identity fallback unless `email_verified` is true.
- Prevents silent/unsafe account merges based on unverified email claims.
- Supports both Google and Facebook with canonical provider normalization.

## Final Validation Performed

- Unit tests executed:
  - `tests/unit/services/test_auth_service_login_guards.py` -> **12 passed**
- App import smoke check:
  - `create_app()` executed successfully.

## Deployment/Run Notes

1. Run migration:
   - `alembic upgrade head`
2. Ensure Cognito Hosted UI has Google/Facebook IdPs configured.
3. Test flows:
   - `GET /api/v1/auth/social-login?provider=google`
   - `GET /api/v1/auth/social-login?provider=facebook`
   - complete callback via `/api/v1/auth/callback?code=...`

## Summary

The codebase now has a production-ready social login foundation with explicit federated identity persistence, deterministic user resolution, secure linking constraints, and compatibility with existing Cognito/JWT/RBAC architecture.
