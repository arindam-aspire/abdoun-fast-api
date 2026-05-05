# 12 — Migrate Admin, Users, RBAC, Dashboard, and Property Assignment

## Goal
Rebuild admin dashboard, user/RBAC management, and admin property assignment.

## Cursor Prompt

```md
Migrate admin/users/RBAC functionality into app_refactored/domains/admin and app_refactored/domains/users.

Legacy capabilities:
Admin dashboard:
- KPIs
- trends
- property performance
- dashboard summary
- recent activity aliases

Users/RBAC:
- list users
- get user
- update user
- delete user
- list roles
- list permissions
- assign role
- remove role

Admin property assignment:
- assign agent to property

Rules:
1. Preserve permission names and role requirements exactly.
2. Preserve pagination and aliases.
3. Preserve response envelopes exactly.
4. Preserve media URL signing behavior in user list/detail.
5. Add startup flags:
   - use_refactored_admin
   - use_refactored_users
6. Update coverage checklist.

Completion checks:
- pytest tests/refactor_parity/test_admin_users_parity.py -q
- pytest tests/smoke/ -q
- python scripts/check_contract_drift.py
```
