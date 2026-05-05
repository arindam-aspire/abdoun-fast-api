# 13 — Migrate Auth and Profile Domain

## Goal
Rebuild auth/profile flows last because it is high-risk and touches Cognito/session behavior.

## Cursor Prompt

```md
Migrate auth/profile functionality into app_refactored/domains/auth.

Legacy capabilities:
- signup
- confirm signup
- resend confirmation
- password login
- OTP request/verify
- refresh
- logout
- forgot password request/confirm
- set password
- change password
- social login
- social callback
- me profile
- profile picture upload if owned by auth router
- profile update request/verify
- permissions

Rules:
1. Preserve Cognito integration boundaries exactly.
2. Do not call real Cognito in parity tests; mock Cognito client/service.
3. Preserve rate limiting decorators and behavior.
4. Preserve token response shape exactly.
5. Preserve error status codes and messages where tests can verify them.
6. Add startup flag use_refactored_auth, default false.
7. Update coverage checklist.
8. Do not switch auth flag until staging login flows are manually verified.

Completion checks:
- pytest tests/refactor_parity/test_auth_parity.py -q
- pytest tests/smoke/ -q
- python scripts/check_contract_drift.py
```
