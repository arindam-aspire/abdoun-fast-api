# 02 — Create app_refactored Package Scaffold

## Goal
Create a clean internal implementation package without changing the live app behavior.

## Cursor Prompt

```md
Create app_refactored/ as a clean implementation package.

Important:
- Do NOT create a second FastAPI production app.
- Do NOT change app/main.py.
- Do NOT include app_refactored routes in the live router yet.
- Do NOT copy SQLAlchemy ORM models.
- app_refactored must import models from app/models/.

Create structure:

app_refactored/
  __init__.py
  core/
    __init__.py
    result.py
    errors.py
  shared/
    __init__.py
    pagination.py
    responses.py
    auth_context.py
  domains/
    __init__.py
    taxonomy/
    properties/
    personalization/
    uploads/
    owners/
    agents/
    submissions/
    admin/
    users/
    auth/
  repositories/
    __init__.py
  services/
    __init__.py

Create docs/refactor/APP_REFACTORED_RULES.md documenting:
- one production app only
- models stay in app/models/
- no DB migrations in app_refactored tasks
- routers are only included through startup-time feature flags later

Completion checks:
- python -c "import app_refactored"
- python -c "from app.main import app"
- No OpenAPI route change
```
