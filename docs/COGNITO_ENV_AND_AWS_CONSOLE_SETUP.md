# Cognito, `.env`, and AWS Console Setup Guide

**Audience:** Operators configuring Abdoun FastAPI authentication (password, OTP, refresh, social login).  
**Sources:** `app/core/config.py`, `.env.example`, `app/services/cognito.py`, social login flow in `app/services/auth_service.py`.

This guide lists **what belongs in `.env`** and **what to configure in AWS** (with console-oriented steps). AWS renames UI labels occasionally; if a label differs slightly, use the search box at the top of the Cognito page for terms like **Hosted UI**, **Callback URL**, or **Identity provider**.

---

## Part 1 — Environment variables (`.env`)

Load order: the app uses `python-dotenv` (`load_dotenv()` in `app/core/config.py`), so variables are typically read from a **`.env`** file in the project root (or parent directories).

### 1.1 Required for Cognito auth (including social login)

| Variable | Required | Description |
|----------|----------|-------------|
| `COGNITO_USER_POOL_ID` | **Yes** | User Pool ID, e.g. `us-east-1_abc123XYZ`. |
| `COGNITO_APP_CLIENT_ID` | **Yes** | App client ID (same as **Client ID** in Cognito). Alias: `COGNITO_CLIENT_ID` also works. |
| `COGNITO_REGION` | No (default `us-east-1`) | Region where the **User Pool** lives. Should match the pool’s region. |
| `COGNITO_DOMAIN` | **Yes** for Hosted UI / social | Cognito **Hosted UI domain** **without** `https://`. Example: `your-prefix.auth.us-east-1.amazoncognito.com`. |
| `SOCIAL_REDIRECT_URI` | **Yes** for social | **Exact** redirect URL used in the OAuth code flow. Must match an **Allowed callback URL** on the app client. Default in code: `http://localhost:8000/api/v1/auth/callback`. Your API route is `GET /api/v1/auth/callback`. |

### 1.2 Optional but common

| Variable | When to set | Description |
|----------|-------------|-------------|
| `COGNITO_APP_CLIENT_SECRET` | If the app client is **confidential** | Client secret. Alias: `COGNITO_CLIENT_SECRET`. If set, Cognito calls (e.g. refresh) may require `SECRET_HASH`; the backend already supports this. |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Local dev or non-IAM roles | Used by **boto3** for `cognito-idp` (login, signup, admin APIs). On **ECS/Lambda/EC2 with instance role**, you can omit these and rely on the role. |
| `AWS_REGION` | Optional | General AWS SDK region (defaults `us-east-1` in config). Align with `COGNITO_REGION` when possible. |

### 1.3 Other app prerequisites (not Cognito-specific)

| Variable | Notes |
|----------|--------|
| `DATABASE_URL` | **Required** for the API to run and persist users; format `postgresql://user:password@host:port/dbname`. |
| `CORS_ORIGINS` | Browser frontends that call the API; must include your real web origin(s). |
| `APP_BASE_URL` | Used for app features such as invite links (not the Cognito OAuth redirect). |
| `PROFILE_OTP_PEPPER` | Profile change phone OTP hashing; set a long random value in production. |

### 1.4 Example `.env` fragment (copy and replace placeholders)

Do **not** commit real secrets. Use `.env` locally and your platform’s secret store in production.

```env
# --- Database ---
DATABASE_URL="postgresql://postgres:password@localhost:5432/abdoun_db"

# --- Cognito (required for auth + social) ---
COGNITO_USER_POOL_ID="us-east-1_XXXXXXXXX"
COGNITO_APP_CLIENT_ID="xxxxxxxxxxxxxxxxxxxxxxxxxx"
COGNITO_REGION="us-east-1"
COGNITO_DOMAIN="your-prefix.auth.us-east-1.amazoncognito.com"

# Must match Cognito app client "Allowed callback URLs" exactly (no trailing slash mismatch)
SOCIAL_REDIRECT_URI="http://localhost:8000/api/v1/auth/callback"

# Only if your app client has a client secret enabled
# COGNITO_APP_CLIENT_SECRET="..."

# Optional: local / CI; use IAM roles in AWS deployments
# AWS_ACCESS_KEY_ID="..."
# AWS_SECRET_ACCESS_KEY="..."
# AWS_REGION="us-east-1"
```

### 1.5 How values are used in this codebase

- **JWT validation (API requests):** JWKS URL is built from `COGNITO_REGION` + `COGNITO_USER_POOL_ID`; access tokens are validated with `audience = COGNITO_APP_CLIENT_ID`.
- **Social login URL:** `https://{COGNITO_DOMAIN}/oauth2/authorize` with `identity_provider=Google` or `Facebook` (see `SocialAuth` in `app/utils/constants.py`).
- **Token exchange (callback):** `POST https://{COGNITO_DOMAIN}/oauth2/token` with `redirect_uri=SOCIAL_REDIRECT_URI` (must match the console).

---

## Part 2 — AWS Console setup (step by step)

Use one **AWS Region** end-to-end (e.g. `us-east-1` or `me-south-1`). The pool, domain, SES (if used), and Lambdas (OTP) should live in that region.

### 2.1 Open Cognito

1. Sign in to the **AWS Management Console**: https://console.aws.amazon.com/
2. In the top search bar, type **Cognito** and open **Amazon Cognito**.
3. Choose **User pools** (not “Identity pools” unless you have a separate mobile use case).

### 2.2 Create or select a User Pool

1. Click **Create user pool** (or select an existing pool).
2. Configure **sign-in options** so users can sign in with **Email** (and optionally phone if you use phone flows).
3. Complete the wizard (password policy, MFA, etc.) per your security policy.
4. After creation, open the pool and copy **User pool ID** → set `COGNITO_USER_POOL_ID`.

### 2.3 Create an App client (for the FastAPI backend)

1. In the left sidebar, open **App integration** (or **Applications** → **App clients**, depending on console version).
2. Under **App clients and analytics**, choose **Create app client** (or **Add app client**).
3. Recommended for this backend:
   - **Authentication flows:** enable at least **ALLOW_USER_PASSWORD_AUTH**, **ALLOW_REFRESH_TOKEN_AUTH**, and **ALLOW_CUSTOM_AUTH** if you use OTP login.
   - **OAuth 2.0** settings (required for Hosted UI / social):
     - Enable **Authorization code grant** (the backend exchanges `code` for tokens).
     - Scopes: include **openid**, **email**, **profile** (matches `get_social_login_url` in code).
4. If you enable a **Client secret**, store it in `COGNITO_APP_CLIENT_SECRET`.
5. Save and copy **Client ID** → `COGNITO_APP_CLIENT_ID`.

### 2.4 Configure the Hosted UI domain (`COGNITO_DOMAIN`)

1. Still under **App integration**, find **Domain** (may appear as **Cognito domain** or **Actions** → **Edit hosted UI**).
2. Choose **Create Cognito domain** (or use a custom domain if your org uses that advanced option).
3. Pick a **prefix** that is globally unique (e.g. `abdoun-api-dev`).
4. After creation, the console shows a domain like:  
   `{prefix}.auth.{region}.amazoncognito.com`  
   Set **`COGNITO_DOMAIN`** to that hostname **without** `https://`.

### 2.5 Callback URL (critical for social login)

1. Open your **App client** → look for **Hosted UI** / **Login pages** / **Edit** (wording varies).
2. Under **Allowed callback URLs**, add the **exact** value of `SOCIAL_REDIRECT_URI`, for example:
   - Local: `http://localhost:8000/api/v1/auth/callback`
   - Production: `https://api.yourdomain.com/api/v1/auth/callback`
3. Under **Allowed sign-out URLs** (if you use logout redirects from Hosted UI), add your frontend URLs as needed.
4. Save changes.

Mismatch here is the **#1** cause of `redirect_uri_mismatch` or social callback failures.

### 2.6 Add Google as an identity provider

**Prerequisite (Google Cloud):**

1. Open **Google Cloud Console** → **APIs & Services** → **Credentials**.
2. **Create credentials** → **OAuth client ID** → Application type **Web application**.
3. Add **Authorized redirect URIs** using Cognito’s redirect (Google documents this as the Cognito `/oauth2/idpresponse` URL). In AWS Cognito, when you add the Google IdP, the console usually shows the **Authorized redirect URI** you must paste into Google — copy it exactly.
4. Note **Client ID** and **Client secret**.

**In AWS Cognito:**

1. In your user pool, open **Sign-in experience** (or **Authentication** / **Federation**).
2. Open **Federated identity provider sign-in** → **Add identity provider** → choose **Google**.
3. Paste Google’s **Client ID** and **Client secret**.
4. Map attributes if prompted (email, name) — defaults usually suffice.
5. Save.

### 2.7 Add Facebook as an identity provider

**Prerequisite (Meta for Developers):**

1. Open https://developers.facebook.com/ → your **App** → **Facebook Login** → **Settings**.
2. Add **Valid OAuth Redirect URIs** using the URI Cognito shows for Facebook (similar to Google’s `/oauth2/idpresponse` pattern).
3. Note **App ID** and **App Secret**.

**In AWS Cognito:**

1. **Add identity provider** → **Facebook**.
2. Enter **App ID** and **App Secret**.
3. Save.

### 2.8 Enable Google and Facebook for your App client (Hosted UI)

1. Go to **App integration** → your **App client** → edit **Hosted UI** / **Login pages** settings.
2. Under **Identity providers**, enable **Google** and **Facebook** (and Cognito user pool / OIDC as needed).
3. Confirm **OAuth 2.0 grant types** still include **Authorization code grant**.
4. Save.

Your backend calls:

- `GET /api/v1/auth/social-login?provider=google` → Cognito `identity_provider=Google`
- `GET /api/v1/auth/social-login?provider=facebook` → `identity_provider=Facebook`

### 2.9 IAM permissions (if using access keys or a dedicated IAM user)

The backend uses **Amazon Cognito Identity Provider** (`cognito-idp`) APIs (e.g. `InitiateAuth`, `SignUp`, `GlobalSignOut`, `AdminCreateUser` for agents).

Attach a policy that allows the needed API actions for your deployment pattern (often a custom policy scoped to your `UserPoolId` and `AppClientId`). For development, some teams use a broader managed policy; for production, **least privilege** is recommended.

If the app runs on **ECS/EKS/EC2/Lambda with an execution role**, prefer the role over long-lived `AWS_ACCESS_KEY_ID` in `.env`.

### 2.10 OTP login (optional; separate from social)

If you use **`/auth/login/otp/*`**, Cognito requires **Lambda triggers** (Define / Create / Verify auth challenge) and usually **SES** for email OTP. See `docs/AUTH_IMPLEMENTATION_AND_AWS_REQUIREMENTS.md` and `cognito-lambda-triggers/` in this repo. Social login does **not** require those Lambdas.

### 2.11 Database migration for social identity rows

After deploying code that includes `social_accounts`, run:

```bash
alembic upgrade head
```

This creates the table used to link Google/Facebook subjects to local users.

---

## Part 3 — Quick verification checklist

| Check | Detail |
|-------|--------|
| `.env` | `COGNITO_USER_POOL_ID`, `COGNITO_APP_CLIENT_ID`, `COGNITO_DOMAIN`, `SOCIAL_REDIRECT_URI` set correctly. |
| Callback | `SOCIAL_REDIRECT_URI` **character-for-character** match in Cognito app client. |
| Region | `COGNITO_REGION` matches the pool region. |
| IdPs | Google and Facebook added in the pool **and** enabled for the app client Hosted UI. |
| Google/Facebook consoles | OAuth redirect URIs match what Cognito displays for each IdP. |
| HTTPS | Production API should use `https://` in `SOCIAL_REDIRECT_URI`. |
| DB | `DATABASE_URL` valid; migration applied for `social_accounts`. |

---

## Part 4 — If something fails

| Symptom | Likely cause |
|---------|----------------|
| `redirect_uri_mismatch` | Callback URL in Google/Facebook or Cognito does not match `SOCIAL_REDIRECT_URI`. |
| Invalid / expired token on API | Wrong pool/client, clock skew, or using **ID token** where the API expects **access token** (`get_current_user`). |
| Social callback 400 “identities” | IdP not returning federated `identities` in the ID token — confirm Hosted UI + Google/Facebook federation on the **same** app client and pool. |
| `SECRET_HASH` / refresh errors | Client has a secret but refresh body missing username — see `ErrorMessages.REFRESH_USERNAME_REQUIRED` in code. |

---

## Related documentation in this repository

- `.env.example` — full list of example variables.
- `docs/AUTH_IMPLEMENTATION_AND_AWS_REQUIREMENTS.md` — SES, OTP Lambdas, broader auth checklist.
- `docs/SOCIAL_LOGIN_IMPLEMENTATION_CHANGE_REPORT.md` — backend social-login code changes.
- `docs/AUTHENTICATION_SYSTEM_REPORT.md` — high-level auth architecture.

---

*AWS console screenshots and exact menu names can change between UI revisions; use Cognito’s in-console help links and the search bar if a step label differs slightly.*
