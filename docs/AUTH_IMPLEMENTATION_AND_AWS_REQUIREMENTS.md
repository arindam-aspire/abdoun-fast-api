# Auth Implementation & AWS Requirements

This document describes **what you need on the AWS side** to implement and run the Abdoun FastAPI authentication (Cognito-based), including **verified/certified email**, OTP (email/SMS), and optional social login. Use it as a single reference for planning and handoff.

---

## Table of Contents

1. [What This Auth Does](#what-this-auth-does)
2. [Login Options: Email/Phone + Password or OTP](#login-options-emailphone--password-or-otp)
3. [Prerequisites](#prerequisites)
4. [AWS Requirements Overview](#aws-requirements-overview)
5. [Email: Certified / Verified Sender (Amazon SES)](#email-certified--verified-sender-amazon-ses)
6. [Cognito User Pool Setup](#cognito-user-pool-setup)
7. [Message Delivery: Cognito vs SES](#message-delivery-cognito-vs-ses)
8. [OTP Login (Lambda + Email/SMS)](#otp-login-lambda--emailsms)
9. [OTP via SMS (Mobile Number)](#otp-via-sms-mobile-number)
10. [App Client & Domain](#app-client--domain)
11. [Optional: Social Login (Google, etc.)](#optional-social-login-google-etc)
12. [Backend Environment (.env)](#backend-environment-env)
13. [Running the Auth](#running-the-auth)
14. [Checklists by Scenario](#checklists-by-scenario)
15. [Related Docs](#related-docs)

---

## What This Auth Does

| Feature | Description |
|--------|-------------|
| **Sign up** | User registers with email, password, name, phone. Cognito sends a verification code by email. |
| **Confirm sign-up** | User enters the code from email; account becomes confirmed. |
| **Login (password)** | Email or phone + password; returns access + refresh tokens. |
| **OTP login** | Passwordless: request OTP → user gets 6-digit code by **email or SMS** → verify code → tokens. |
| **Forgot password** | Request code by email → confirm with code + new password. |
| **Refresh / Logout** | Refresh token for new access token; logout invalidates session. |
| **Social login** | Optional: Google (or Apple/Facebook) via Cognito Hosted UI; callback returns tokens. |

Identity and tokens are handled by **AWS Cognito**. User records, roles, and permissions live in **your database** and are enforced by the FastAPI backend.

---

## Login Options: Email/Phone + Password or OTP

The API supports:

- **Password login**: Client sends `username` (email or E.164 phone) + `password`. Backend resolves to the user and calls Cognito with email.
- **Passwordless (OTP)**: Client sends `username` (email or phone) → backend requests OTP → Lambda sends code by **email (SES)** or **SMS (SNS)** → client sends same `username` + `session` + `code` → tokens.

One field (`username`) accepts either email or phone; no separate endpoints.

---

## Prerequisites

- **AWS account** with access to:
  - Amazon Cognito (User Pools)
  - Amazon SES (Simple Email Service) — for production/reliable email and OTP
  - AWS Lambda (for OTP custom auth)
  - Amazon SNS (optional, for OTP via SMS)
- **Region**: All resources (Cognito, SES, Lambda) should be in the **same region** (e.g. **me-south-1** for Bahrain).
- **Backend**: Python 3.x, `.env` for secrets, PostgreSQL for users/roles.

---

## AWS Requirements Overview

| Area | Required for | What you need |
|------|----------------|---------------|
| **Cognito User Pool** | All auth | Create pool: email sign-in, self sign-up, email verification, required attributes (email, name, phone_number). |
| **Cognito App Client** | All auth | Confidential client; enable USER_PASSWORD_AUTH, REFRESH_TOKEN_AUTH, CUSTOM_AUTH (for OTP). |
| **Cognito Domain** | Hosted UI / social login | Create Cognito domain (prefix) for OAuth URLs. |
| **Email (sign-up / forgot password)** | Verification & reset emails | Either **Cognito** (easiest for testing) or **SES** (verified sender; sandbox vs production). |
| **SES verified identities** | Reliable / production email | Verify at least one **sender** (From) in SES; in sandbox, verify **recipients** too or request production. |
| **Lambda triggers (3)** | OTP login only | Define Auth Challenge, Create Auth Challenge, Verify Auth Challenge Response. |
| **SES for OTP** | OTP email delivery | Create Auth Challenge Lambda sends OTP via SES; needs verified sender + Lambda IAM (or use test mode: OTP in CloudWatch). |
| **SNS for OTP SMS** | OTP to mobile | Optional: Lambda sends OTP via SNS; enable SMS and set ENABLE_SMS_OTP on Lambda. |
| **Social IdP (e.g. Google)** | Social login only | Create OAuth client in Google, add IdP in Cognito, set redirect URI. |

---

## Email: Certified / Verified Sender (Amazon SES)

For **production** and **reliable deliverability**, send email through **Amazon SES** with a **verified identity** (certified/authorized sender).

### Why verify?

- **Cognito “Send email with Cognito”**: No verification needed; Cognito sends from its own address. Limited volume; may land in spam.
- **“Send email with Amazon SES”**: You must **verify** the sender (and in sandbox, recipients). Better deliverability and control once set up.

### What “verified” means in SES

| Identity type | What you do | Use case |
|---------------|-------------|----------|
| **Email address** | Add the From address in SES → AWS sends a verification email → you click the link. | Single sender (e.g. `noreply@yourdomain.com` or your email for testing). |
| **Domain** | Add your domain in SES → add DNS records (DKIM, etc.) as shown by AWS. | Sending from any address at that domain. |

### SES Sandbox vs production

| | Sandbox | Production |
|--|--------|------------|
| **Sender** | Must be a verified identity (email or domain). | Same. |
| **Recipients** | Only **verified** recipient addresses receive email. | Can send to **any** address (within limits). |
| **How to get production** | Open **AWS Support** → **Open a case** → request **SES sending limit increase / production access**. Provide use case (e.g. sign-up verification, OTP). |

**For certified/production-ready email:**

1. **Verify a sender** in SES (email or domain) in the **same region** as Cognito.
2. For **sign-up / forgot-password**: In Cognito message delivery, choose **Send email with Amazon SES** and use that verified identity.
3. For **OTP**: The Create Auth Challenge Lambda uses SES; set Lambda env `SES_FROM_EMAIL` to a verified sender and give the Lambda `ses:SendEmail` permission.
4. For **sending to any user** (not only test addresses): Request **SES production access** and complete any requested verification.

---

## Cognito User Pool Setup

Detailed steps are in [AWS_COGNITO_SETUP.md](AWS_COGNITO_SETUP.md). Summary of **your** responsibilities:

1. **Create User Pool** (same region as Lambda/SES).
2. **Sign-in**: Email (and optionally phone).
3. **Sign-up**: Self-registration **on**; required attributes: **email**, **name**, **phone_number**.
4. **Verification**: **Turn on email verification** so Cognito sends a code on sign-up.
5. **Message delivery**: Either “Send email with Cognito” (quick test) or “Send email with Amazon SES” (verified sender).
6. **MFA**: Typically “No MFA” unless you add it later.
7. **App client**: Created in same wizard or under App integration (see [App Client & Domain](#app-client--domain)).

---

## Message Delivery: Cognito vs SES

| Option | Pros | Cons | When to use |
|--------|------|------|-------------|
| **Send email with Cognito** | No SES setup; works to any address within limits. | Daily limits; may go to spam. | Development / first testing. |
| **Send email with Amazon SES** | Better deliverability; your From address/domain. | Must verify sender (and in sandbox, recipients). | Staging / production. |

If you use SES for Cognito (sign-up/forgot-password), set the **FROM** address in the User Pool messaging settings to a **verified SES identity** (same region).

---

## OTP Login (Lambda + Email/SMS)

OTP uses **Cognito custom auth** with **three Lambda triggers**. The **Create Auth Challenge** Lambda generates the 6-digit code and sends it by **email (SES)** and/or **SMS (SNS)**.

### Your responsibilities

1. **Create 3 Lambda functions** (same region as Cognito), Python 3.11/3.12:
   - **Define Auth Challenge** — when to show OTP challenge and when to issue tokens.
   - **Create Auth Challenge** — generate code, store it, send by email (SES) and/or SMS (SNS).
   - **Verify Auth Challenge Response** — check user’s code against stored value.
2. **Attach** all three to the User Pool under **Lambda triggers**.
3. **Create Auth Challenge**:
   - For **email**: set Lambda env **SES_FROM_EMAIL** to a **verified SES sender**; attach **AmazonSESFullAccess** (or `ses:SendEmail`) to the Lambda role.
   - For **SMS**: set **ENABLE_SMS_OTP=true** and attach **sns:Publish** to the Lambda role (see [OTP via SMS](#otp-via-sms-mobile-number)).
   - For **test without SES**: set **SKIP_SES_FOR_TESTING=true** and get OTP from **CloudWatch Logs** (never in production).
4. **App client**: Ensure **ALLOW_CUSTOM_AUTH** is enabled.

Lambda code is in **`cognito-lambda-triggers/`** in this repo. For **step-by-step** Lambda creation and attachment (current AWS console), see **[COGNITO_OTP_LAMBDA_SETUP.md](COGNITO_OTP_LAMBDA_SETUP.md)**.

---

## OTP via SMS (Mobile Number)

You can send the OTP to the user’s **mobile number (SMS)**. The client sends **phone number** (E.164) as `username`; the backend resolves to the Cognito user (email), and the **Create Auth Challenge** Lambda can send the code via **Amazon SNS** to `userAttributes.phone_number`.

- **Lambda**: Set env **ENABLE_SMS_OTP** = `true`; optional **OTP_CHANNEL_PREFERENCE** = `sms` or `email`. Give the Lambda **sns:Publish** (e.g. AmazonSNSFullAccess or custom policy).
- **Cognito**: User must have **phone_number** attribute (E.164). Sign-up already stores it.
- **SNS**: SMS must be enabled for your account and target countries (see AWS SNS SMS docs).

---

## App Client & Domain

### App client (backend)

- **Type**: **Confidential** (client secret generated).
- **Auth flows**: **ALLOW_USER_PASSWORD_AUTH**, **ALLOW_REFRESH_TOKEN_AUTH**, **ALLOW_CUSTOM_AUTH** (for OTP).
- **Callback URL(s)**: Must include your backend callback, e.g. `http://localhost:8000/api/v1/auth/callback` (and production URL when you have it).
- Store **Client ID** and **Client secret** in `.env`; the backend uses them for Cognito API calls and SECRET_HASH.

### Cognito domain

- Create a **Cognito domain** (prefix) for the User Pool so you get a URL like `https://<prefix>.auth.<region>.amazoncognito.com`.
- Used for **Hosted UI** and **social login**. Put the full domain (no `https://`) in `.env` as **COGNITO_DOMAIN**.

---

## Optional: Social Login (Google, etc.)

To allow “Sign in with Google” (or Apple/Facebook):

1. **Google Cloud Console**: Create OAuth 2.0 client (Web application), add **Authorized redirect URI**:  
   `https://<COGNITO_DOMAIN>/oauth2/idpresponse`
2. **Cognito**: Add **Google** (or other IdP) under Sign-in experience / Federation; enter Client ID and Client secret; map attributes (e.g. email, name).
3. **App client**: In Hosted UI settings, enable the **Google** identity provider.
4. Backend exposes **GET /api/v1/auth/social-login?provider=Google** and **GET /api/v1/auth/callback?code=...**.

Same region and callback URL consistency (Cognito ↔ Google ↔ `.env`) are required.

---

## Backend Environment (.env)

Your side must provide (see `.env.example`):

| Variable | Description | Example |
|----------|-------------|---------|
| **COGNITO_REGION** | AWS region of User Pool (and SES/Lambda). | `me-south-1` |
| **COGNITO_USER_POOL_ID** | User pool ID from Cognito. | `me-south-1_AbCdEfGhI` |
| **COGNITO_APP_CLIENT_ID** | App client ID. | From App integration. |
| **COGNITO_APP_CLIENT_SECRET** | App client secret (confidential client). | From App integration. |
| **COGNITO_DOMAIN** | Full Cognito domain, no `https://`. | `abdoun-auth.auth.me-south-1.amazoncognito.com` |
| **SOCIAL_REDIRECT_URI** | Must match an App client callback URL. | `http://localhost:8000/api/v1/auth/callback` |
| **APP_BASE_URL** | Frontend/base URL (e.g. for invite links). | `http://localhost:3000` |
| **CORS_ORIGINS** | Allowed origins (comma-separated). | `http://localhost:3000` |
| **DATABASE_URL** | PostgreSQL connection string. | `postgresql://user:pass@host:5432/db` |

No AWS-side change is needed for these; they are your configuration only.

---

## Running the Auth

1. **Database**: Migrations applied; run **`python scripts/seed_rbac.py`** once so roles and permissions exist.
2. **.env**: All Cognito (and optional SES) variables set as above.
3. **Start API**: e.g. `uvicorn app.main:app --reload` (or your usual run).
4. **Test**: Use Postman or the auth endpoints (sign-up → confirm → login → /auth/me).

Flow: Sign up → confirm with code from email → login (password or OTP) → use `access_token` as Bearer for protected routes.

---

## Checklists by Scenario

### Minimal (password-only auth, no OTP, no social)

- [ ] AWS: Cognito User Pool (email sign-in, self sign-up, email verification on).
- [ ] Message delivery: “Send email with Cognito” (or SES with verified sender).
- [ ] App client: Confidential; USER_PASSWORD_AUTH + REFRESH_TOKEN_AUTH; callback URL set.
- [ ] Cognito domain created; ID, secret, domain in `.env`.
- [ ] Backend: `.env` set; DB migrated; `seed_rbac.py` run; API running.

### Full (password + OTP + optional social)

- [ ] Everything in **Minimal**.
- [ ] SES: At least one verified **sender** (email or domain) in same region (for OTP and/or Cognito messaging).
- [ ] Lambda: All 3 triggers created and attached; Create Auth Challenge has **SES_FROM_EMAIL** and SES permission (or test mode with CloudWatch). Optional: **ENABLE_SMS_OTP** and SNS for OTP via mobile.
- [ ] App client: **ALLOW_CUSTOM_AUTH** enabled.
- [ ] Optional social: Google (or other) IdP in Cognito; redirect URI in Google; IdP enabled in App client.

### Production (reliable email to any user)

- [ ] SES: **Verified sender** (prefer domain + DKIM).
- [ ] SES: **Production access** requested and approved (so you can send to unverified recipients).
- [ ] Cognito message delivery: “Send email with Amazon SES” with verified FROM.
- [ ] OTP Lambda: **SES_FROM_EMAIL** set to verified sender; **SKIP_SES_FOR_TESTING** not set.
- [ ] Callback and CORS use production URLs; secrets and `.env` not committed.

---

## Related Docs

| Document | Purpose |
|----------|---------|
| [AWS_COGNITO_SETUP.md](AWS_COGNITO_SETUP.md) | Step-by-step Cognito User Pool, app client, domain, optional social. |
| [COGNITO_OTP_LAMBDA_SETUP.md](COGNITO_OTP_LAMBDA_SETUP.md) | Step-by-step: create and attach the three OTP Lambda triggers; test without SES (CloudWatch) or with SES. |
| Verification email troubleshooting (repo) | Sign-up verification email not received. |
| Postman / API testing (repo) | How to test all auth endpoints. |

---

**Summary**: You need a **Cognito User Pool + App Client + Domain** and **.env** for basic auth. For **certified/reliable email** (sign-up, forgot-password, OTP), use **Amazon SES** with **verified identities** and, for sending to any user, **SES production access**. OTP additionally requires **three Lambda triggers** and, for real OTP email/SMS, **SES** and optionally **SNS** configured on the Create Auth Challenge Lambda.
