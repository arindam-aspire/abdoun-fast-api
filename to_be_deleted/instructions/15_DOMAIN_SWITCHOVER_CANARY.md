# 15 — Domain Switchover and Canary Plan

## Goal
Switch domains one at a time behind startup flags after parity is proven.

## Cursor Prompt

```md
Create a controlled switchover plan and implement only the requested domain switch.

Rules:
1. Never enable more than one new refactored domain at a time in staging.
2. Production default remains legacy unless explicitly changed in deployment env.
3. Switching means:
   - set feature flag true
   - restart process
   - run smoke tests
   - run frontend smoke flows
   - check logs
4. Rollback means:
   - set feature flag false
   - restart process

Create docs/refactor/CANARY_SWITCHOVER_PLAN.md with:
- domain order
- required tests per domain
- rollback command
- owner approval checklist

Do not enable flags by default in code.

Completion checks:
- all flags default false
- check_contract_drift passes when all flags false
- route inventory generated with each flag true in isolation
```
