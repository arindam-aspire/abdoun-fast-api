# Real User Auth E2E Test Guide

This guide gives you a no-confusion way to test the full auth flow like a real user.

## Files provided

- `docs/Postman_Auth_E2E_Real_User_Collection.json`
- `docs/Postman_Auth_E2E_Real_User_Environment.json`

Import both into Postman.

---

## 1) Prerequisites (must be true first)

1. Backend is running on `http://localhost:8000`.
2. `.env` has correct Cognito values:
   - `COGNITO_DOMAIN` must be host only (no `https://`)
   - `SOCIAL_REDIRECT_URI=http://localhost:8000/api/v1/auth/callback`
3. Cognito App Client (Managed login) has:
   - Identity providers: `Google` (and/or `Facebook`)
   - OAuth grant: `Authorization code grant`
   - Scopes: `openid`, `email`, `profile`
   - Callback URL: `http://localhost:8000/api/v1/auth/callback`
4. Google OAuth client has authorized redirect URI:
   - `https://<your-cognito-domain>/oauth2/idpresponse`
   - Example: `https://us-west-2uu25kznbm.auth.us-west-2.amazoncognito.com/oauth2/idpresponse`
5. DB migration is applied:
   - `alembic upgrade head`

---

## 2) Import and set Postman environment

1. Import collection: `Postman_Auth_E2E_Real_User_Collection.json`
2. Import environment: `Postman_Auth_E2E_Real_User_Environment.json`
3. Select environment `Abdoun Auth E2E Local`
4. Edit these variables:
   - `test_email` (use an email you can receive OTP/confirmation on)
   - `test_phone_e164` (example `+15551234567`)
   - `test_password`

---

## 3) Test password flow end-to-end

Run requests in this order:

1. `1) Signup`
2. `2) Confirm Signup`
   - Put real confirmation code in env var `signup_code`
3. `3) Password Login`
   - Automatically stores `access_token`, `refresh_token`, `id_token`
4. `4) Me (Bearer access token)`
5. `5) Refresh`
6. `9) Logout`

If these pass, core auth flow is healthy.

---

## 4) Test social flow end-to-end (real browser user)

### Google

1. Run `6) Social Login URL (Google)`
2. Copy env variable `social_google_url` from Postman console / environment
3. Open that URL in browser
4. Complete Google login
5. You should be redirected to:
   - `http://localhost:8000/api/v1/auth/callback?code=...`
6. If you already see token JSON in browser, social flow is complete.

### Optional manual callback exchange in Postman

If you want to call callback manually from Postman:

1. Copy `code` from browser redirect URL
2. Set env var `social_code`
3. Run `8) Callback Exchange (manual social code)`
4. Tokens are saved automatically in environment
5. Run `4) Me (Bearer access token)` to confirm token works

### Facebook

Same process with request `7) Social Login URL (Facebook)`.

---

## 5) Expected success responses

- Login/callback should return:
  - `access_token`
  - `refresh_token` (may be absent in some token refresh responses)
  - `id_token`
  - `expires_in`
- `/auth/me` should return current user profile.

---

## 6) Fast troubleshooting map

- `redirect_uri_mismatch` (Google page):  
  Google OAuth client missing `https://<cognito-domain>/oauth2/idpresponse`

- `invalid_scope` in callback URL:  
  Managed login scopes missing `profile` (must include `openid email profile`)

- Callback returns `code field required`:  
  Cognito returned an error instead of `?code=...`; inspect URL query params.

- `https://https://...` in social login URL:  
  `COGNITO_DOMAIN` incorrectly includes `https://`.

- `/auth/me` says invalid token:  
  Use `access_token` in Bearer header, not `id_token`.

---

## 7) Real-user completion checklist

- [ ] Signup + confirm works
- [ ] Password login returns tokens
- [ ] `/auth/me` works with access token
- [ ] Refresh works
- [ ] Google social login reaches callback with `code`
- [ ] Callback returns tokens
- [ ] `/auth/me` works with social access token
- [ ] (Optional) Facebook flow also passes

