# 09 — Migrate Owners Domain

## Goal
Rebuild owner and property-owner mapping CRUD without changing live auth behavior.

## Cursor Prompt

```md
Migrate owners functionality into app_refactored/domains/owners.

Legacy capabilities:
- owner create/list/get/update/delete
- property-owner mapping create/update/delete

Important:
- Preserve current auth behavior exactly, even if it is unsafe.
- Do not add auth in this task unless legacy already has it.
- Add a security note to docs/refactor/SECURITY_DEBT_REGISTER.md if owners are unauthenticated.

Rules:
1. Implement refactored repository/service/router.
2. Use app/models/ existing ORM models only.
3. For write parity, use rollback if possible.
4. If rollback is unreliable, compare status + response shape and flag DB effect as not fully verified.
5. Add startup flag use_refactored_owners, default false.
6. Update coverage checklist.

Completion checks:
- pytest tests/refactor_parity/test_owners_parity.py -q
- pytest tests/smoke/ -q
- python scripts/check_contract_drift.py
```
