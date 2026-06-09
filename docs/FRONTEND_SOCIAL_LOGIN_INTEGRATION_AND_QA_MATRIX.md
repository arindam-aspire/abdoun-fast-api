# Frontend Social Login Integration and QA Matrix

This document defines the backend contract for social login and provides a practical test matrix for frontend QA and client UAT.

## 1) Backend Contract (Social Login)

### 1.1 Start social auth

- Endpoint: `GET /api/v1/auth/social-login?provider=<provider>`
- Supported providers: `google`, `facebook` (case-insensitive)
- Success: `200` with `StandardResponse` where `data.url` is the Cognito Hosted UI URL

Frontend behavior:

1. Call endpoint with selected provider.
2. Redirect browser to `response.data.url`.

### 1.2 Handle callback

- Endpoint: `GET /api/v1/auth/callback?code=<authorization_code>`
- Success response type: `StandardResponse[TokenResponse]`

Expected token payload fields:

- `access_token` (string)
- `refresh_token` (string | null)
- `id_token` (string | null)
- `token_type` (`Bearer`)
- `expires_in` (int, seconds)
- `requires_password_set` (bool; expected `false` for normal social login)

Frontend behavior:

1. Read callback `code`.
2. Call backend callback endpoint.
3. Persist tokens via your app's existing secure token strategy.
4. Call `GET /api/v1/auth/me` with `Authorization: Bearer <access_token>`.
5. Route to authenticated app.

### 1.3 Refresh session

- Endpoint: `POST /api/v1/auth/refresh`
- Body:
  - `refresh_token` (required)
  - `username` (optional, but required in environments where Cognito app client uses a secret)

Frontend behavior:

- Keep current refresh strategy.
- If refresh fails, clear local auth state and route to login.

## 2) Frontend Error Mapping

Map backend `detail` messages to clear UI actions.

- `Unsupported social provider. Use google or facebook.`
  - UI: "This provider is not supported."
  - Action: show available providers only.

- `Identity provider did not return federated identity information (identities claim). Ensure Google/Facebook sign-in uses Cognito Hosted UI with a supported IdP.`
  - UI: "Social sign-in failed. Please try again."
  - Action: retry option + fallback login methods.

- `Email is required from the identity provider to register a new account.`
  - UI: "Your social account must provide an email address."
  - Action: ask user to use a provider account with email.

- `An account with this email already exists. Sign in with your existing method, or complete email verification with your social provider before linking.`
  - UI: "An account already exists with this email."
  - Action: prompt login via existing method (password/OTP).

- `This social account is already linked to another user.`
  - UI: "This social account is linked to a different account."
  - Action: retry with correct account or contact support.

- `Phone login is not available for this account. Add and verify a phone number first.`
  - UI: "Phone login is not enabled for this account yet."
  - Action: prompt user to login via email/social and complete phone setup/verification in profile.

- Existing guard errors (inactive/deleted user)
  - UI: "Your account is unavailable."
  - Action: show support contact flow.

## 3) QA Test Matrix

Use this as a single-pass validation plan for frontend QA and client testing.

### 3.1 Core success flows

1. **Google login success (existing linked user)**
   - Step: click Google -> complete consent -> callback.
   - Expected: callback returns tokens, `/me` succeeds, user lands in app.

2. **Facebook login success (existing linked user)**
   - Same expected result as Google.

3. **First-time social login creates new account**
   - Preconditions: no existing local user by `cognito_sub`, no social link, no conflicting email.
   - Expected: backend creates user + social link + default role, returns tokens, `/me` succeeds.

4. **Existing user link by verified email**
   - Preconditions: existing user with same email and provider returns `email_verified=true`.
   - Expected: account links correctly, no duplicate user created, login succeeds.

### 3.2 Validation and edge cases

5. **Unsupported provider input**
   - Step: call `/social-login?provider=twitter`.
   - Expected: `400` with unsupported provider detail.

6. **Missing callback code**
   - Step: open callback route without `code`.
   - Expected: validation error; frontend shows retry path.

7. **Missing identities claim in social token**
   - Expected: `400` with identities-related error detail.

8. **Unsupported identity provider in token**
   - Expected: `400` unsupported provider detail.

9. **New social user without email**
   - Expected: `400` email-required detail.

10. **Email conflict on new social user**
    - Preconditions: local account already exists with same email but cannot be safely linked under rules.
    - Expected: `409` conflict detail, no duplicate account.

11. **Social identity already linked to another user**
    - Expected: `409` identity conflict detail.

12. **Inactive user attempts social login**
    - Expected: `403` inactive detail.

13. **Soft-deleted user attempts social login**
    - Expected: `403` deleted-account detail.

### 3.3 Session lifecycle checks

14. **Phone login attempted for account without phone_number**
    - Preconditions: account exists but `phone_number` is not set.
    - Step: try password or OTP login with phone identifier.
    - Expected: `400` with "Phone login is not available..." detail.

15. **Access protected endpoint after login**
    - Step: call `/api/v1/auth/me`.
    - Expected: `200` with current user profile.

16. **Refresh token flow**
    - Step: call `/refresh` using social refresh token.
    - Expected: new access token issued (and app session continues).

17. **Logout flow**
    - Step: call `/logout` with valid bearer token.
    - Expected: logout success response; frontend clears state.

### 3.4 Resilience and UX checks

18. **Double-click social button**
    - Expected: no broken state in UI; one final successful session.

19. **Callback replay / page refresh on callback route**
    - Expected: deterministic frontend behavior (idempotent handling in UI), no duplicate local session artifacts.

20. **Network failure during callback exchange**
    - Expected: user sees retriable error screen and fallback login options.

21. **Network failure during `/me` after token issuance**
    - Expected: token remains stored; frontend supports retry before forcing logout.

## 4) Frontend Implementation Checklist

- [ ] Social buttons only expose Google and Facebook.
- [ ] `/social-login` provider query is passed in lowercase (`google` or `facebook`).
- [ ] Frontend redirects to backend-provided Hosted UI URL.
- [ ] Callback route extracts `code` and calls backend `/callback`.
- [ ] Tokens are persisted using existing secure auth storage strategy.
- [ ] Authenticated bootstrap call to `/me` is performed after callback success.
- [ ] Error mapper handles all social-specific backend `detail` messages.
- [ ] Refresh flow supports optional `username` for client-secret environments.
- [ ] Logout clears local auth state regardless of backend response timing.
- [ ] Analytics/logging captures provider, success/failure reason, and retry attempts.

## 5) Client UAT Sign-off Template

- Environment tested:
- Providers tested: Google / Facebook
- New user signup via social: Pass / Fail
- Existing user login via social: Pass / Fail
- Conflict handling messages verified: Pass / Fail
- Refresh and logout behavior verified: Pass / Fail
- Overall readiness for production pilot: Pass / Fail

