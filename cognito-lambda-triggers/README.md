# Cognito OTP Lambda Triggers (Python)

These are the three **Python** Lambda function sources for **Cognito custom auth (OTP login)**. Copy them into the AWS Lambda console (or deploy via zip), then attach the Lambdas to your User Pool triggers.

**Full step-by-step setup:** [docs/COGNITO_OTP_LAMBDA_SETUP.md](../docs/COGNITO_OTP_LAMBDA_SETUP.md).

## Files and handlers

| Trigger | File | Lambda name in AWS | Handler |
|--------|------|--------------------|---------|
| Define Auth Challenge | `define_auth_challenge.py` | cognito-define-auth-challenge | `define_auth_challenge.handler` |
| Create Auth Challenge | `create_auth_challenge.py` | cognito-create-auth-challenge | `create_auth_challenge.handler` |
| Verify Auth Challenge Response | `verify_auth_challenge_response.py` | cognito-verify-auth-challenge | `verify_auth_challenge_response.handler` |

Use **Runtime: Python 3.11** (or 3.12) for each function.

**Create Auth Challenge:** Set `FROM_EMAIL` (or env `SES_FROM_EMAIL`) to your SES verified sender and attach SES send permission for real email. **To test without SES:** leave the placeholder or set env `SKIP_SES_FOR_TESTING=true`; the OTP will be logged to CloudWatch. See the guide section "Test without SES".
