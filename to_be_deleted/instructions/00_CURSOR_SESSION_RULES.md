# 00 — Cursor Session Rules

Paste this at the start of every Cursor session.

```md
You are working on Abdoun Property Management System, a LIVE FastAPI + PostgreSQL + SQLAlchemy + Alembic application.

Critical rules:
1. There is only ONE production FastAPI app: app.main:app.
2. Do NOT run two production apps side by side in the same Uvicorn process.
3. app_refactored/ is a clean internal implementation package only. It does not own app startup.
4. Routes are switched only at startup by conditional include_router in app/api/v1/router.py.
5. Never hot-swap routers per request.
6. SQLAlchemy models remain in app/models/ during this migration. app_refactored/ must import existing models from app/models/.
7. Do not copy ORM model definitions into app_refactored/.
8. Do not change any live API method, path, request shape, response shape, auth rule, or DB behavior unless the current task explicitly allows it.
9. Do not edit existing Alembic migrations. Only create new migrations when a task says so.
10. Every migrated domain must pass parity tests before it can be switched behind a startup flag.
11. For authenticated endpoint parity, use the shared fake_current_user override from tests/refactor_parity/conftest.py.
12. For write endpoints, use transaction rollback when possible. If rollback isolation is not reliable, compare status code + response shape only and flag DB-effect parity as MANUAL_REVIEW_REQUIRED.
13. After every file change, run: python -c "from app.main import app"
14. After every task, run:
    - pytest tests/smoke/ -q
    - pytest tests/refactor_parity/ -q
    - python scripts/check_contract_drift.py
15. If functionality is discovered in legacy code but not implemented in app_refactored/, add it to docs/refactor/MISSING_FUNCTIONALITY_REGISTER.md and do not switch that domain.
16. Prefer minimal diffs. Change only what the current task asks.
17. If uncertain, stop and write a blocking note in docs/refactor/BLOCKERS.md.
```
