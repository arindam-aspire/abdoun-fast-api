# Backend Implementation Prompt — Auth, Roles, Agent Flow & Cognito

**Use this document as-is:** copy and paste it into any AI tool (Cursor, Antigravity, etc.) so the tool can implement or refine the backend accurately. Do not modify the requirements below; implement according to them. Design for **readability**, **maintainability**, **no security risks**, and **easy future changes** (including DB schema and API changes).

---

## 1. User Types

- **Admin user** — Full admin capabilities; can onboard other admins, manage agents, assign/revoke agent-to-admin.
- **Agent user** — Can be invited by an admin; after approval, can inherit admin privileges if assigned by that admin.
- **Registered user** — Normal portal user (sign-up/sign-in); has only registered-user permissions.

One user can have **multiple roles**. Permissions are resolved from all roles (and, for agents, from inherited admin permissions when assigned).

---

## 2. Admin User Onboarding

- **Single endpoint** for onboarding an admin (e.g. `POST /api/v1/auth/signup/admin`).
- Use the **same JSON payload** as normal user registration/sign-up (e.g. full name, email, phone with country code, password).
- Only difference: assign role **Admin** instead of Registered User.
- Validate all inputs (format, duplicates) before creating; return clear error messages and log failures.

---

## 3. Agent–Admin Assignment and Revocation

- An **admin** can **assign** an agent to themselves so that agent gets the benefits of that admin’s role (e.g. inherited permissions).
- The same admin can **revoke** that assignment; after revocation, the agent no longer has those inherited privileges.
- Revocation applies **only** to agents who were **assigned** to that admin (i.e. “converted” to have admin-like access). It does **not** apply to users who were onboarded as admins from the beginning.

Provide **separate endpoints**, e.g.:
- `POST /api/v1/agents/assign-agent` (body: admin_id, agent_id or similar).
- `POST /api/v1/agents/unassign-agent` (body: admin_id, agent_id or similar).

Use permission checks (e.g. only users with `agent:assign` or admin role) and return proper errors and logs.

---

## 4. Sign-In / Login (Already Registered Users)

Use **separate endpoints** for each login method (industry practice: one concern per URL).

### 4.1 Social login

- Support **Google**, **Facebook**, **Apple** (or equivalent IdPs).
- Follow industry best practice (e.g. OAuth 2.0 / OIDC with Cognito Hosted UI or equivalent).
- Endpoints typically:
  - `GET /api/v1/auth/social-login?provider=Google|Facebook|Apple` — returns redirect URL to IdP.
  - `GET /api/v1/auth/callback` — OAuth callback; exchange code for tokens; create or link local user by stable id (e.g. Cognito sub / email); return tokens and user info.

### 4.2 Form login (email/phone + password)

- **Inputs:** email **or** phone number (phone must include **country code**, e.g. E.164), and password.
- **Flow:**
  1. Validate **format** of email or phone (and country code). If invalid → return **400** with clear error message and log.
  2. Check if a user with that email/phone **exists**. If not → return **404** (or 401) with “user does not exist” (or equivalent) and log.
  3. If valid and exists → perform login (e.g. Cognito `USER_PASSWORD_AUTH`); return tokens and user info.
- Endpoint example: `POST /api/v1/auth/login/password` (body: username [email or E.164 phone], password).
- **Always** return proper error messages and add logs for validation and auth failures.

### 4.3 One-time code (OTP) login

- **Input:** email **or** phone number (with country code).
- **Flow:**
  1. Validate **format** of email or phone. If invalid → return **400** with clear error and log.
  2. Check if user **exists**. If not → return “user does not exist” and log.
  3. If exists → send OTP to that email/phone; return session (or similar) for the next step.
  4. Second step: verify OTP (e.g. `POST /api/v1/auth/login/otp/verify` with session + code) and return tokens.
- Use **separate endpoints**, e.g.:
  - `POST /api/v1/auth/login/otp/request` — validate input, check existence, send OTP.
  - `POST /api/v1/auth/login/otp/verify` — verify code and return tokens.
- Always validate input format first; then existence; then send OTP. Use proper error messages and logging.

---

## 5. Sign-Up / Create Account (New Users)

- Before creating: **check if user already exists** (e.g. by email/phone). If exists → return “user already exists” (e.g. 409) and do not create.
- Use **separate endpoints** per sign-up method.

### 5.1 Social sign-up

- Same providers as login (Google, Facebook, Apple); industry-standard OAuth/OIDC flow.
- On first login via social: create local user, assign **Registered user** role, apply permissions for that role.
- Reuse or align with social **login** callback so that “first time” creates the user and “existing” just logs in.

### 5.2 Form sign-up

- **Required fields (as of now):** full name, email, phone number (with **country code**), password.
- **Password policy:** at least 8 characters; at least one uppercase letter; one lowercase letter; one number; one special character.
- **Flow:**
  1. Validate **all** input formats (email, phone with country code, password policy). If any invalid → return **400** with clear, field-level error messages and log.
  2. Check user does not already exist (email/phone). If exists → return “user already exists” and log.
  3. Create user in auth provider (e.g. Cognito) and in application DB; assign **Registered user** role; apply permissions for that role.
- Endpoint example: `POST /api/v1/auth/signup` (body: full_name, email, phone_number, password).
- Always return proper error messages and add logs.

---

## 6. Input Validation and Logging

- **Every** endpoint that accepts payload or query input must **validate format first** (email, phone E.164, password rules, etc.).
- If validation fails → return **4xx** with a **clear, user-facing error message** and **log** the failure (e.g. validation error, “user not found”, “invalid token”).
- Do not proceed to business logic or DB with invalid input. Keep validation in one place (e.g. Pydantic schemas + explicit checks) for readability and future changes.

---

## 7. Role Assignment on Sign-Up

- When a user is successfully created via **sign-up** (form or social), assign them the **Registered user** role.
- Apply only the permissions granted to the Registered user role for all portal operations until additional roles are assigned.

---

## 8. Security

- Ensure **no security risks**: no sensitive data in logs (e.g. passwords, tokens); use HTTPS; validate and sanitize all inputs; use parameterized queries / ORM; enforce auth and permission checks on every protected route.
- Store passwords only in the auth provider (e.g. Cognito); do not store plain or reversibly encrypted passwords in application DB.
- Use short-lived access tokens and secure refresh flow; invalidate sessions on logout.

---

## 9. Roles and Permissions

- **Permissions** are the unit of access control (e.g. `user:create`, `agent:approve`, `agent:assign`, `property:create`).
- **Roles** are groups of permissions. A user can have **multiple roles**; effective permissions = union of all role permissions + (for agents) inherited permissions from admin assignment when applicable.
- **As of now:** assume industry best practice for which role gets which permission (e.g. Admin: full; Agent: limited + inheritable; Registered: basic). Document the mapping so it can be changed later when you have formal documentation.

---

## 10. Agent Creation and Onboarding Flow

- **Context:** A person (candidate agent) gives their email to an admin. The admin sends them an **invite link** to that email. The link is **valid only for that email** and **time-limited** (e.g. 7 days). After expiry, the link is invalid.

### 10.1 Invite creation (admin)

- Endpoint e.g. `POST /api/v1/agents/invite` (body: email).
- Auth: only admin (or permission such as `agent:approve`).
- Create an invite record: email, unique token, expiry, invited_by (admin). Return the **invite link** (or token) so the client/backend can send it by email. Do not expose internal IDs in the link if not needed.

### 10.2 Invite validation (public, for the form)

- Endpoint e.g. `GET /api/v1/agents/invite/validate?token=...` (no auth).
- If token is valid (exists, not used, not expired) → return success and **email** (so the form can prefill or display it). If invalid → return clear error and log.

### 10.3 Agent registration form (submit)

- User opens the form from the link; form fields (all required for now): **Full name**, **Phone number (with country code)**, **Service area**; submit button.
- Endpoint e.g. `POST /api/v1/agents/register` (body: token, full_name, phone_number, service_area). Email is **not** in the body; it is fixed by the invite (token).
- **Flow:**
  1. Validate token (valid, not used, not expired). If invalid → error and log.
  2. Validate input **formats** (full name, phone E.164, service_area). If invalid → return clear errors and log.
  3. Create user in application DB (inactive/pending); create agent profile (e.g. status=pending); assign Agent role; mark invite as used. Do **not** create Cognito user yet (done on approval).
  4. Return success and send or enqueue “submitted for approval” (e.g. to admin). If you have a notification system, trigger “pending approval” for admin.

### 10.4 Admin approval

- Endpoint e.g. `POST /api/v1/agents/{agent_id}/approve` (auth: admin or `agent:approve`).
- On approval: create user in Cognito (if not already), set user active, set agent profile status to approved, set approved_by/approved_at. Then **notify the agent** (e.g. email or in-app) that they are onboarded as an agent.

### 10.5 Agent login after onboarding

- After approval, the agent can log in. **As of now:** allow login **only via OTP** (email/phone). Do **not** allow password login for agents unless you explicitly add it later. Use the same OTP request/verify endpoints as other users, with permission or role checks if needed.

### 10.6 Rejection (optional but recommended)

- Provide e.g. `POST /api/v1/agents/{agent_id}/reject` so admin can reject a pending agent; set status to rejected and optionally notify the candidate. Keep DB and APIs easy to extend (e.g. status enum: pending, approved, rejected).

---

## 11. API and URL Design

- Use **separate endpoints** for each distinct operation (e.g. signup, signup/admin, login/password, login/otp/request, login/otp/verify, agents/invite, agents/invite/validate, agents/register, agents/assign-agent, agents/unassign-agent, agents/{id}/approve, agents/{id}/reject). Avoid overloading a single URL with many optional behaviors.
- Use REST-style URLs and HTTP methods (GET for read, POST for create/action). Keep URLs stable so future changes (e.g. new optional fields) can be done without breaking clients.

---

## 12. Database Design

- Design tables so that **CRUD**, **queries**, and **schemas** are straightforward and **easy to change later**.
- Suggested concepts (adapt to your ORM):
  - **users** — id, auth_provider_id (e.g. Cognito sub), email, phone_number, full_name, is_active, is_email_verified, is_phone_verified, created_at, updated_at.
  - **roles** — id, name, description.
  - **permissions** — id, code, description.
  - **role_permissions** — role_id, permission_id (many-to-many).
  - **user_roles** — user_id, role_id, assigned_by, assigned_at (many-to-many).
  - **agent_profiles** — user_id (FK), service_area, status (e.g. pending/approved/rejected), approved_by, approved_at.
  - **agent_invites** — id, email, invited_by (user_id), token, expires_at, is_used, created_at.
  - **admin_agent_assignments** — id, admin_id, agent_id, is_active, can_inherit_privileges, assigned_at, revoked_at (or equivalent).
- Use indexes on lookup fields (email, phone, token, admin_id, agent_id). Avoid storing passwords in application DB; use auth provider only.

---

## 13. AWS Cognito

- Use Cognito for: user pool, app client, sign-up, sign-in (password, OTP, social), token issuance and validation.
- **Password auth:** use Cognito `USER_PASSWORD_AUTH` or equivalent for form login.
- **OTP:** use Cognito custom auth flow (e.g. Define Auth Challenge, Create Auth Challenge, Verify Auth Challenge) with Lambda triggers to send and verify OTP (email/SMS). Backend calls InitiateAuth (CUSTOM_AUTH) and then RespondToAuthChallenge with the code.
- **Social:** use Cognito Identity Provider with Google/Facebook/Apple as IdPs (e.g. Hosted UI) and map IdP attributes to Cognito user attributes; link to application user by Cognito sub or email.
- **Admin creation of agents:** after admin approves an agent, create the Cognito user with `AdminCreateUser` (or equivalent); do not set a permanent password if agents use only OTP; use “invite” or “force password change” only if you add password login for agents later.
- Validate JWTs (access token, ID token) in the backend using Cognito’s JWKS; use `cognito_sub` (or equivalent) to resolve the application user and enforce roles/permissions.

---

## 14. Future Changes

- This is **not** the final specification. Design so that:
  - New roles or permissions can be added without rewriting auth.
  - New login/sign-up methods or optional form fields can be added with minimal changes.
  - Agent flow can be extended (e.g. password login for agents, extra approval steps, notifications) without breaking existing flows.
  - DB schema and API versioning (e.g. `/api/v1/`) allow backward-compatible changes.

---

**Summary for the AI:** Implement (or refine) the backend so that: (1) user types and roles (Admin, Agent, Registered) and permissions are clear and extensible; (2) admin onboarding, agent invite/register/approve/reject and assign/unassign use separate endpoints and are secure; (3) sign-up and sign-in support form (email/phone + password, OTP) and social (Google, Facebook, Apple) with strict validation and logging; (4) DB and Cognito are aligned with the above; (5) code is readable, maintainable, and easy to modify later.
