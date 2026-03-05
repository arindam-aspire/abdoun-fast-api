# OTP Login — Create and Configure Lambda Triggers (Step-by-Step)

This guide walks you through creating the **three Lambda functions** for Cognito OTP login and attaching them to your User Pool. It uses the **current AWS Console** (Lambda and Cognito) so you can follow along click-by-click.

**Before you start:** Complete [AWS_COGNITO_SETUP.md](AWS_COGNITO_SETUP.md) Parts 1–5 (User pool, App client, Domain, `.env`). All three Lambdas must be in the **same AWS region** as your Cognito User Pool (e.g. **Middle East (Bahrain) me-south-1**).

---

## What You Will Create

| Lambda function | Purpose |
|-----------------|--------|
| **Define Auth Challenge** | Tells Cognito to show the OTP challenge and when to issue tokens. |
| **Create Auth Challenge** | Generates a 6-digit code, stores it, and sends it by email (SES) or logs it for testing. |
| **Verify Auth Challenge Response** | Checks the code the user entered; tells Cognito if it is correct. |

**Test without email:** You can test without configuring SES. The Create Auth Challenge Lambda will log the OTP to **CloudWatch Logs** so you can copy the code from there (see **Part 6**).

---

# Part 1 — Open Lambda and Choose Region

1. In the **AWS Management Console**, use the **top search bar** and type **Lambda**.
2. Click **Lambda** (under Services) to open the Lambda console.
3. In the **top-right corner**, check the **region**. Click it to change if needed. Choose the **same region** as your Cognito User Pool (e.g. **me-south-1**).

---

# Part 2 — Create the Three Lambda Functions

Use the **Runtime** and **Handler** in the table below for each function. Code is in the repo folder **`cognito-lambda-triggers/`** (`.py` files).

| Lambda | Runtime | Handler |
|--------|---------|---------|
| Define Auth Challenge | Python 3.11 or 3.12 | `define_auth_challenge.handler` |
| Create Auth Challenge | Python 3.11 or 3.12 | `create_auth_challenge.handler` |
| Verify Auth Challenge Response | Python 3.11 or 3.12 | `verify_auth_challenge_response.handler` |

---

## 2.1 Create Lambda 1: Define Auth Challenge

1. On the **Functions** page, choose **Create function** (you’ll see breadcrumb: **Lambda > Functions > Create function**).
2. Under **Create function**, select **Author from scratch** (description: “Start with a simple Hello World example”).
3. In the **Basic information** section:
   - **Function name:** type `cognito-define-auth-challenge` (must be 1–64 characters, unique in the region; only letters, numbers, hyphens, underscores).
   - **Runtime:** open the dropdown and choose **Python 3.11** (or **Python 3.12**). The console code editor supports Node.js, Python, and Ruby.
   - **Architecture:** leave **x86_64** selected (do not switch to arm64).
4. In the **Permissions** section (below Basic information):
   - Leave **Create default role** selected. AWS will create a role named like `cognito-define-auth-challenge-role-xxxxx` so the function can upload logs to CloudWatch. You do not need “Use another role” for this trigger.
5. In **Additional configurations** (Function URL, VPC, etc.):
   - Leave **Function URL** and **VPC** **unchecked**. Leave **Tenant isolation mode**, **Code signing**, **Encryption with KMS**, and **Tags** unchecked. No changes needed for these Cognito triggers.
6. At the bottom, choose **Create function** (orange button). Do not choose Cancel.
7. After the function is created, set the **Handler**:
   - Go to the **Code** tab (not Configuration).
   - In the **Code** tab, look for a section called **Runtime settings** (often above or to the right of the code editor). It shows **Runtime** (e.g. Python 3.11) and **Handler** (e.g. `lambda_function.lambda_handler`).
   - Click **Edit** in that **Runtime settings** section. A small form or panel opens where you can change the **Handler**.
   - Set **Handler** to: `define_auth_challenge.handler`
   - Choose **Save**.
   - *If you don’t see Runtime settings on the Code tab:* Open **Configuration** → **General configuration**. Some consoles show **Runtime** and **Handler** there with a separate **Edit** (for runtime/handler only). Use that Edit to set Handler to `define_auth_challenge.handler`.
8. In the **Code** tab, in the **file explorer** (left side of the code editor), you will see a file such as `lambda_function.py`. **Rename it** to `define_auth_challenge.py` (right-click the file → **Rename**, or click the filename and type the new name).
9. **Delete all code** inside the file and **paste** the contents of **`cognito-lambda-triggers/define_auth_challenge.py`** from this repo (or the code block below).
10. Choose **Deploy** (orange button in the Code tab).

**Code for Define Auth Challenge** (if not copying from repo):

```python
def handler(event, context):
    session = event["request"].get("session", [])

    if len(session) == 0:
        event["response"]["challengeName"] = "CUSTOM_CHALLENGE"
        event["response"]["issueTokens"] = False
        event["response"]["failAuthentication"] = False
        return event

    last = session[-1]
    if last.get("challengeName") == "CUSTOM_CHALLENGE" and last.get("challengeResult") is True:
        event["response"]["challengeName"] = None
        event["response"]["issueTokens"] = True
        event["response"]["failAuthentication"] = False
        return event

    if len(session) >= 3:
        event["response"]["challengeName"] = None
        event["response"]["issueTokens"] = False
        event["response"]["failAuthentication"] = True
        return event

    event["response"]["challengeName"] = "CUSTOM_CHALLENGE"
    event["response"]["issueTokens"] = False
    event["response"]["failAuthentication"] = False
    return event
```

---

## 2.2 Create Lambda 2: Create Auth Challenge

1. Back on the **Functions** page, choose **Create function** again.
2. Select **Author from scratch**.
3. In **Basic information:** **Function name** `cognito-create-auth-challenge`, **Runtime** Python 3.11, **Architecture** x86_64.
4. In **Permissions:** leave **Create default role** selected. In **Additional configurations**, leave Function URL, VPC, and the rest **unchecked**.
5. Choose **Create function** (orange button).
6. Set the **Handler**: **Configuration** → **General configuration** → **Edit** → **Handler:** `create_auth_challenge.handler` → **Save**.
7. **(Only if you will send real email later)** Give this function permission to send email:
   - **Configuration** → **Permissions** → click the **Role name** (opens IAM in a new tab).
   - In IAM: **Add permissions** → **Attach policies** → search **AmazonSESFullAccess** → check it → **Add permissions**. Close the IAM tab.
   - For **test without SES**, skip this step.
8. In the **Code** tab, **rename** the default file to `create_auth_challenge.py`, then **paste** the contents of **`cognito-lambda-triggers/create_auth_challenge.py`** from this repo.
9. For **test without SES:** Do nothing else. The code will log the OTP to CloudWatch when no verified sender is set.
   For **real email later:** **Configuration** → **Environment variables** → **Edit** → **Add environment variable**: Key **SES_FROM_EMAIL**, Value **your SES-verified email** → **Save**.
10. Choose **Deploy**.

---

## 2.3 Create Lambda 3: Verify Auth Challenge Response

1. On the **Functions** page, choose **Create function** again.
2. Select **Author from scratch**.
3. In **Basic information:** **Function name** `cognito-verify-auth-challenge`, **Runtime** Python 3.11, **Architecture** x86_64.
4. In **Permissions** and **Additional configurations**, leave defaults (Create default role; Function URL, VPC, etc. unchecked). Choose **Create function**.
5. Set the **Handler**: **Configuration** → **General configuration** → **Edit** → **Handler:** `verify_auth_challenge_response.handler` → **Save**.
6. In the **Code** tab, **rename** the default file to `verify_auth_challenge_response.py`, then **paste** the contents of **`cognito-lambda-triggers/verify_auth_challenge_response.py`** from this repo.
7. Choose **Deploy**.

---

# Part 3 — Attach the Lambdas to Your User Pool (Cognito)

1. In the **top search bar**, type **Cognito** and open **Amazon Cognito**.
2. In the left sidebar, click **User pools**.
3. Click **your user pool name** (e.g. abdoun-user-pool) to open it.
4. In the left menu of the user pool, click **User pool properties** (or in some consoles, the triggers section is under the main overview). Scroll to the **Lambda triggers** section (sometimes labeled **Triggers**). If you do not see it, look for **Triggers** or **Lambda triggers** in the left navigation.
5. Under **Authentication**, you will see:
   - **Define auth challenge**
   - **Create auth challenge**
   - **Verify auth challenge response**
6. For each row, open the dropdown and select the matching Lambda:
   - **Define auth challenge** → **cognito-define-auth-challenge**
   - **Create auth challenge** → **cognito-create-auth-challenge**
   - **Verify auth challenge response** → **cognito-verify-auth-challenge**
7. Choose **Save changes**.
8. If AWS prompts to **add permissions** so Cognito can invoke these Lambdas, choose **Confirm** or **Add permission**. This allows the User Pool to call the three functions.

---

# Part 4 — Ensure App Client Allows Custom Auth

1. In the **same User pool** page, in the left menu click **App integration** (or **App clients and analytics**).
2. In the list of app clients, click **your app client name** (e.g. abdoun-backend).
3. Scroll to **Authentication flows** (or **Security** / **Hosted UI** in some UIs). Ensure **ALLOW_CUSTOM_AUTH** is **enabled** (checked). If not, enable it.
4. Choose **Save changes** if you changed anything.

---

# Part 5 — Test OTP Login (End-to-End)

Use your API base URL (e.g. **http://localhost:8000** when running locally). Send requests with **Content-Type: application/json**.

**Step A — Ensure a user exists**

- The user must exist in **Cognito** and in **your app database**. If not: sign up via **POST** `http://localhost:8000/api/v1/auth/signup` with body `{ "email": "...", "password": "...", "full_name": "...", "phone_number": "..." }`, then confirm with **POST** `http://localhost:8000/api/v1/auth/confirm-signup` using the code from email.

**Step B — Request OTP**

- **Method:** POST  
- **URL:** `http://localhost:8000/api/v1/auth/login/otp/request`  
- **Body (JSON):** `{ "username": "your-email@example.com" }`  
- **Response:** You will get JSON like `{ "success": true, "data": { "session": "..." }, "message": "..." }`. **Copy the value of `data.session`** for the next step.

**Step C — Get the 6-digit code**

- **If using SES for email:** Check the user’s email inbox (and spam).
- **If using test without SES:** See **Part 6** below (get code from CloudWatch Logs).

**Step D — Verify OTP**

- **Method:** POST  
- **URL:** `http://localhost:8000/api/v1/auth/login/otp/verify`  
- **Body (JSON):** `{ "session": "<paste data.session from Step B>", "username": "your-email@example.com", "code": "123456" }`  
  Replace `123456` with the actual code from Step C.  
- **Response:** You should receive JSON with `data.access_token`, `data.refresh_token`, and `data.expires_in`.

---

# Part 6 — Test without SES (OTP from CloudWatch)

You can test the full OTP flow **without configuring Amazon SES**.

1. When creating the **Create Auth Challenge** Lambda (Part 2.2), **do not** set **SES_FROM_EMAIL**. Do **not** attach SES permissions. The code in `cognito-lambda-triggers/create_auth_challenge.py` will then log the OTP instead of sending email.
2. After you call **POST .../auth/login/otp/request** (Part 5, Step B):
   - In the AWS Console, open **Lambda** → **Functions** → **cognito-create-auth-challenge**.
   - Open the **Monitor** tab, then choose **View CloudWatch logs**.
   - Open the **latest log stream**. In the log output, find a line like:  
     `[OTP for testing] email=your-email@example.com code=123456`
   - Copy the 6-digit **code** (e.g. `123456`).
3. Use that code in **POST .../auth/login/otp/verify** (Part 5, Step D) with the **session** from Step B.

**Production:** For real email, configure SES (see [AWS_COGNITO_SETUP.md](AWS_COGNITO_SETUP.md) and [AUTH_IMPLEMENTATION_AND_AWS_REQUIREMENTS.md](AUTH_IMPLEMENTATION_AND_AWS_REQUIREMENTS.md)), set **SES_FROM_EMAIL** to a verified sender, and attach **AmazonSESFullAccess** (or `ses:SendEmail`) to the Create Auth Challenge Lambda role. Do not leave test mode enabled.

---

# Troubleshooting

- **"Custom auth lambda trigger is not configured"**  
  One or more triggers are not attached to the User Pool, or the wrong Lambda was selected. Re-check Part 3 and save again.

- **No email received**  
  If you are testing without SES, get the code from CloudWatch (Part 6). If using SES, ensure the recipient is verified in SES (sandbox) and **SES_FROM_EMAIL** is set to a verified identity.

- **Invalid or expired OTP**  
  Use the **session** returned by `/login/otp/request` in `/login/otp/verify`; it expires after a few minutes. Enter the code with no spaces. After 3 wrong attempts, request a new OTP.

- **Handler or file name**  
  The Handler must match the filename and function (e.g. `define_auth_challenge.handler` for file `define_auth_challenge.py`). Check **Configuration** → **General configuration** → **Handler**.

---

# Quick Checklist

- [ ] **Region:** Lambda and Cognito in the same region.
- [ ] **Lambda 1:** cognito-define-auth-challenge, Python 3.11, Handler `define_auth_challenge.handler`, code deployed.
- [ ] **Lambda 2:** cognito-create-auth-challenge, Python 3.11, Handler `create_auth_challenge.handler`, code deployed; for test mode leave SES unset; for email set SES_FROM_EMAIL and SES permission.
- [ ] **Lambda 3:** cognito-verify-auth-challenge, Python 3.11, Handler `verify_auth_challenge_response.handler`, code deployed.
- [ ] **Cognito:** All three triggers attached (Part 3); permissions confirmed.
- [ ] **App client:** ALLOW_CUSTOM_AUTH enabled (Part 4).
- [ ] **Test:** Request OTP → get code (email or CloudWatch) → verify OTP → receive tokens.

After this, **POST /api/v1/auth/login/otp/request** and **POST /api/v1/auth/login/otp/verify** work with your FastAPI backend.
