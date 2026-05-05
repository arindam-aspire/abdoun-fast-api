# 07 — Migrate Personalization Domain

## Goal
Rebuild favorites, saved searches, and recent views with auth parity.

## Cursor Prompt

```md
Migrate personalization functionality into app_refactored/domains/personalization.

Legacy capabilities:
Favorites:
- add/list/remove/bulk add

Saved searches:
- create/list/get/update/delete/execute/bulk create

Recent views:
- add/list/remove/clear

Rules:
1. Use shared fake_current_user override for parity tests.
2. Do not require real Cognito in parity tests.
3. Preserve property_hash vs property_id behavior exactly.
4. Preserve bulk behavior exactly.
5. For write endpoints:
   - Use rollback transaction if possible.
   - Otherwise compare status + response shape and record DB-effect limitation.
6. Add startup flag use_refactored_personalization, default false.
7. Update functionality checklist.

Completion checks:
- pytest tests/refactor_parity/test_personalization_parity.py -q
- pytest tests/smoke/ -q
- python scripts/check_contract_drift.py
```
