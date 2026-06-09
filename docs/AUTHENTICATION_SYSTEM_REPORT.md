# Authentication System Report

**Scope:** Existing FastAPI backend — Cognito, PostgreSQL, JWT validation, routes, and dependencies.  
**Generated:** 2026-05-04

---

## 1. High-level model

The API is **stateless for callers**: it does **not** issue its own JWTs or maintain server sessions. **AWS Cognito** is the identity provider. The application stores a **local `User`** row (PostgreSQL) linked by `cognito_sub`, and protected routes resolve the user from a **Bearer access token** validated against Cognito’s JWKS.

---

## 2. PostgreSQL / ORM: user and RBAC

Core account data lives on `User` (`users` table): `cognito_sub`, `email`, `phone_number`, verification flags, `is_active`, soft delete (`deleted_at`), optional `AgentProfile`, and many-to-many `roles` / `permissions` via `user_roles` and `role_permissions`.

**Reference:** `app/models/user.py` — class `User`, `Role`, `Permission`, `AgentProfile`, `AgentInvite`, `AdminAgentAssignment`.

Migrations such as `alembic/versions/0014_add_authentication_and_rbac_models.py` introduced `cognito_sub` and related RBAC structures.

---

## 3. Cognito integration (`CognitoService`)

**File:** `app/services/cognito.py`

Wraps **boto3 `cognito-idp`**: signup, confirm, `USER_PASSWORD_AUTH`, `CUSTOM_AUTH` (OTP), `REFRESH_TOKEN_AUTH`, forgot password, Hosted UI URL plus **authorization code → token** exchange (`requests` to the Cognito domain), `global_sign_out`, and admin flows for agents.

### Token verification

The service fetches the pool **JWKS** (cached approximately 24 hours), then uses **`jwt.decode`** (python-jose) with **RS256**, **`aud`** = app client id, and the Cognito **issuer** URL:

- JWKS URL pattern: `https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json`
- Issuer: `https://cognito-idp.{region}.amazonaws.com/{user_pool_id}`

Optional **client secret** is supported via `SECRET_HASH` on Cognito API calls where required.

---

## 4. Auth routes (signup / login / session)

Routes are mounted under **`/api/v1` + `/auth`** (see `ApiRoutes` in `app/utils/constants.py` and `app/api/v1/router.py`).

**Router:** `app/api/v1/routes/auth.py`  
**Service:** `app/services/auth_service.py`

| Area | Endpoints (representative) | Role |
|------|---------------------------|------|
| Signup | `POST /signup`, `POST /confirm-signup`, `POST /resend-confirmation` | Cognito signup + local `User` + default role |
| Password login | `POST /login/password` | Local user lookup by email **or** phone; Cognito auth uses **`user.email`** as Cognito username |
| OTP login | `POST /login/otp/request`, `POST /login/otp/verify` | `CUSTOM_AUTH` (expects pool Lambda triggers; see `cognito-lambda-triggers/`) |
| Tokens | `POST /refresh` | `REFRESH_TOKEN_AUTH`; may require `username` in body when client has a secret |
| Logout | `POST /logout` | `global_sign_out` with current access token |
| Password | `POST /forgot-password/request`, `POST /forgot-password/confirm`, `POST /set-password`, `POST /change-password` | Cognito + optional `password_set_at` on `AgentProfile` |
| Social | `GET /social-login?provider=google` or `facebook`, `GET /callback` | Hosted UI → code exchange → ID token; federated identity in `social_accounts`; resolution order: `cognito_sub` → `(provider, provider_user_id)` → verified email link → new user |
| Profile / RBAC (authenticated) | `GET /me`, `GET /me/permissions`, profile picture and profile update routes | Require valid access token |

### Social identity storage (`social_accounts`)

Federated IdP subjects are stored in **`social_accounts`** (`app/models/social_account.py`, migration `0039_social_accounts`): `user_id`, canonical **`provider`** (`google` or `facebook`), **`provider_user_id`** (from Cognito ID token `identities[0].userId`), unique on `(provider, provider_user_id)`. Email-based linking runs **only** when **`email_verified`** is true on the ID token; new accounts require a non-empty **email** in the token.

### Guards and sync

- **`_ensure_user_login_allowed`:** Blocks inactive or soft-deleted users before returning tokens (login, OTP verify, refresh, social for existing users).
- **`_sync_verified_flags_from_token_payload`:** Updates `is_email_verified` / `is_phone_verified` on `User` from token claims during explicit auth flows (login, refresh, social). The **`get_current_user` dependency is intentionally read-only** for user-sync writes.

---

## 5. Token generation and validation

| Concern | Implementation |
|--------|----------------|
| **Generation** | Cognito only (`initiate_auth`, `respond_to_auth_challenge`, Hosted UI token endpoint). API returns `access_token`, `refresh_token`, `id_token`, `expires_in` in `TokenResponse`. |
| **Protected routes** | `get_current_user` in `app/core/auth.py`: `HTTPBearer` → `cognito_service.verify_token` → require **`token_use == "access"`** → load `User` by `cognito_sub`, else email from claims or Cognito `admin_get_user` by sub → reject if missing user → **403** if `not user.is_active`. |
| **Optional auth** | `get_current_user_optional` — `HTTPBearer(auto_error=False)`; returns `None` when no Authorization header (e.g. some property routes). |

**Important:** ID tokens are **not** accepted by `get_current_user`; only access tokens with `token_use == "access"`.

---

## 6. Dependencies, RBAC, middleware

| Component | Location | Behavior |
|-----------|----------|----------|
| `get_current_user`, `get_current_user_optional`, `security` | `app/core/auth.py`; re-exported `app/api/v1/deps/security.py` | Cognito JWT + DB user resolution |
| `require_role`, `require_permission`, `get_user_permissions` | `app/core/permissions.py` | `Depends(get_current_user)` then role/permission checks; supports **admin→agent inheritance** via `AdminAgentAssignment` when `can_inherit_privileges` is true |
| Auth service wiring | `app/api/v1/deps/auth.py` | `AuthService` + `AuthRepository` + `MediaUrlSigner` |

**Middleware:** There is **no global auth middleware** in `app/main.py`. Present middleware includes CORS, `RequestIdMiddleware`, `SecurityHeadersMiddleware`, and optional Prometheus metrics — none perform JWT parsing.

**Rate limiting:** `slowapi` limits on signup and several auth endpoints (`app/core/limiter.py`, decorators on auth routes).

---

## 7. Supporting pieces

| Piece | File / area |
|-------|-------------|
| User lookups, create user, roles, social account rows | `app/repositories/auth_repository.py` |
| Agent Cognito user creation | `app/services/agent_service.py` |
| Config (pool, client, region, domain, redirect) | `app/core/config.py`, environment / `docker-compose.yml` |

---

## 8. One-sentence summary

**Cognito owns credentials and tokens; the FastAPI app validates Cognito access JWTs (JWKS, RS256, access-only on API dependencies), maps `sub` to a PostgreSQL `User`, and layers RBAC with `require_role` / `require_permission` — with no first-party session store and no auth-specific middleware beyond security headers and rate limiting.**

---

## 9. Key code references

**User model (excerpt):** `app/models/user.py` — `User` with `cognito_sub`, `email`, `phone_number`, verification flags, `is_active`, `deleted_at`, relationships to `Role` and `AgentProfile`.

**JWT dependency (excerpt):** `app/core/auth.py` — `get_current_user`: `verify_token`, `token_use == "access"`, resolve by `cognito_sub` or email fallback, active check.

**Token verification (excerpt):** `app/services/cognito.py` — `verify_token`: JWKS lookup, `jwt.decode` with `audience=self.client_id` and Cognito issuer.

---

*This document describes the system as implemented in the repository at the time of writing. For AWS pool setup and operational requirements, see `docs/AUTH_IMPLEMENTATION_AND_AWS_REQUIREMENTS.md`.*
