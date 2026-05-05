# 04 — Startup-Time Route Switching Policy

## Goal
Prepare safe feature-flag route switching, but do not switch any domain yet.

## Cursor Prompt

```md
Implement a startup-time route-switching policy.

Rules:
- Routing decision happens only during import/startup in app/api/v1/router.py.
- No request-time route hot swapping.
- No second production app.
- Default flags must keep legacy routes.

Add settings flags in app/core/config.py or existing settings location:
- use_refactored_taxonomy: bool = False
- use_refactored_properties: bool = False
- use_refactored_personalization: bool = False
- use_refactored_uploads: bool = False
- use_refactored_owners: bool = False
- use_refactored_agents: bool = False
- use_refactored_submissions: bool = False
- use_refactored_admin: bool = False
- use_refactored_users: bool = False
- use_refactored_auth: bool = False

Do not wire any refactored router yet unless a later domain task instructs it.

Create docs/refactor/FEATURE_FLAG_CUTOVER_POLICY.md:
- default false
- staging first
- one domain at a time
- parity tests required
- rollback = set flag false and restart process

Completion checks:
- python -c "from app.main import app"
- python scripts/check_contract_drift.py must show no route changes
```
