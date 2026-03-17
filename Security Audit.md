# Security Audit — End-to-End Step-by-Step Refactor Plan

This document is the refactor plan for the **Security Audit** section (lines 108–182) of `FINAL_FASTAPI_BACKEND_AUDIT.md`. Each step is ordered so that dependencies are respected and changes can be validated incrementally.

---

## Summary of Findings Addressed

| # | Finding | Risk | Fix |
|---|--------|------|-----|
| 1 | Unauthenticated admin signup (`POST /api/v1/auth/signup/admin`) | Full system compromise | Require existing admin authentication |
| 2 | Missing rate limiting on auth endpoints | Credential stuffing, OTP brute force, API abuse | Use slowapi (or Redis) with limits e.g. 5/minute |
| 3 | Security headers missing | XSS, clickjacking, MIME sniffing | Add middleware for X-Frame-Options, X-Content-Type-Options, HSTS, CSP |
| 4 | CORS `allow_origins = ["*"]` with credentials | Insecure in production | Production must use explicit origins; enforce per environment |

---

## Step-by-Step Refactor Plan

### Step 1 — Secure Admin Signup Endpoint

**Goal:** Require existing admin authentication for `POST /api/v1/auth/signup/admin`.

**Actions:**

1. In `app/api/v1/routes/auth.py`, add dependency `require_role(UserRoles.ADMIN)` to the `signup_admin` endpoint (same pattern as in `app/api/v1/routes/agents.py`).
2. Import `require_role` and `UserRoles` (from `app.api.v1.deps.security` and `app.utils.constants`).
3. Update the endpoint docstring to state that admin authentication is required.
4. Run auth/contract tests to ensure unauthenticated and non-admin calls return 401/403 and admin calls succeed.

**Deliverables:** Admin signup is only callable by an authenticated admin user.

---

### Step 2 — Add Rate Limiting for Auth Endpoints

**Goal:** Protect login, OTP, and forgot-password flows from brute force and abuse.

**Actions:**

1. Add `slowapi` to `requirements.txt`.
2. In `app/main.py` (or a dedicated middleware/limiter module): create a `Limiter` with `key_func=get_remote_address`, attach to `app.state.limiter`, and register `RateLimitExceeded` exception handler.
3. Apply rate limit decorators to the following auth routes (e.g. `limit("5/minute")` or stricter for OTP):
   - `POST /auth/login/password`
   - `POST /auth/login/otp/request`
   - `POST /auth/login/otp/verify`
   - `POST /auth/forgot-password/request` (and optionally `forgot-password/confirm`)
   - Optionally `POST /auth/signup` and `POST /auth/signup/admin` with a slightly higher limit (e.g. 10/minute).
4. Ensure `Request` is injected where the limiter needs it (per slowapi docs).
5. Add or adjust tests to verify 429 when limit exceeded.

**Deliverables:** Critical auth endpoints are rate limited per IP; 429 returned when limit exceeded.

---

### Step 3 — Add Security Headers Middleware

**Goal:** Set recommended security headers on all responses.

**Actions:**

1. Add `app/middleware/` package if it does not exist (e.g. `__init__.py`).
2. Create `app/middleware/security.py` with a `SecurityHeadersMiddleware` (Starlette `BaseHTTPMiddleware`) that sets:
   - `X-Content-Type-Options: nosniff`
   - `X-Frame-Options: DENY`
   - `X-XSS-Protection: 1; mode=block`
   - `Referrer-Policy: strict-origin-when-cross-origin`
   - `Strict-Transport-Security: max-age=31536000; includeSubDomains` only when not in debug/local (use `app.core.config` environment).
   - Optionally a minimal `Content-Security-Policy` (e.g. `default-src 'self'`) if appropriate for the API.
3. Register the middleware in `app/main.py` after CORS (so it runs after CORS in the stack).
4. Optionally add a quick test that requests a known endpoint and asserts the headers are present.

**Deliverables:** All responses include the security headers; HSTS only in non-debug environments.

---

### Step 4 — Harden CORS Configuration

**Goal:** Ensure production never uses `allow_origins = ["*"]` with credentials; use explicit origins per environment.

**Actions:**

1. In `app/core/config.py`: keep `cors_origins` from `CORS_ORIGINS` env (CSV). If `ENVIRONMENT` is `production` or `staging`, treat empty or `"*"` as invalid and either raise at startup or fall back to a safe default (e.g. empty list so that misconfiguration fails visibly). Document in docstring or comments.
2. In `.env.example`, set `CORS_ORIGINS` to explicit dev origins (e.g. `http://localhost:3000,http://127.0.0.1:3000`) and add a comment that production must set explicit origins.
3. Optionally add a startup check in `create_app()` that, when `cors_allow_credentials` is True and environment is production/staging, ensures `"*"` is not in `cors_origins` (log warning or fail fast).
4. Update any deployment/docs to state that `CORS_ORIGINS` must be set explicitly in production.

**Deliverables:** Production and staging cannot use wildcard CORS with credentials; config and docs are clear.

---

## Order of Execution

Execute in this order:

1. **Step 1** — Secure admin signup (no new dependencies).
2. **Step 2** — Rate limiting (add slowapi, then apply to auth routes).
3. **Step 3** — Security headers middleware (new middleware, register in main).
4. **Step 4** — CORS hardening (config and startup checks).

Steps 2, 3, and 4 are independent of each other after Step 1; they can be done in sequence and each validated with a quick smoke test.

---

## Verification Checklist

- [ ] Unauthenticated `POST /api/v1/auth/signup/admin` → 401.
- [ ] Authenticated non-admin `POST /api/v1/auth/signup/admin` → 403.
- [ ] Authenticated admin `POST /api/v1/auth/signup/admin` → 200 (with valid body).
- [ ] Auth endpoints return 429 after exceeding rate limit.
- [ ] All responses include `X-Frame-Options`, `X-Content-Type-Options`, and (in prod) `Strict-Transport-Security`.
- [ ] Production/staging reject or warn on `CORS_ORIGINS=*` when credentials are enabled.
- [ ] Existing tests and API contracts still pass.

---

## References

- `FINAL_FASTAPI_BACKEND_AUDIT.md` (Security Audit section, lines 108–182)
- `.ai/fastapi_backend/references/security.md` (rate limiting, CORS, security headers)
- `.cursor/rules/02-security-resilience.mdc` (abuse protection, rate limiting)
