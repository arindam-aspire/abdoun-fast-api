# 01 — Baseline Snapshot and Functionality Inventory

## Goal
Create a reliable baseline from the live app before any parallel implementation starts.

## Cursor Prompt

```md
Create the baseline safety net for the live FastAPI app.

Tasks:
1. If docs/FUNCTIONALITY_MATRIX.md does not exist, generate it by introspecting:
   - app/api/v1/router.py
   - all app/api/v1/routes/*.py
   - app/services/
   - app/repositories/
   - app/schedulers/
   - scripts/
2. If docs/CODEBASE_CURRENT_STATE.md does not exist, generate it from the current repository structure.
3. Export current OpenAPI to docs/refactor/openapi_legacy_baseline.json.
4. Export current DB schema to docs/refactor/db_schema_legacy_baseline.json using SQLAlchemy inspect().
5. Create docs/refactor/ROUTE_INVENTORY.json containing every method/path/response_model/auth dependency if discoverable.
6. Create docs/refactor/FUNCTIONALITY_COVERAGE_CHECKLIST.md with one checklist section per domain:
   - Auth & profile
   - Users & RBAC
   - Agents
   - Admin dashboard
   - Properties
   - Geo search/import
   - Taxonomy
   - Submissions
   - Agent property list
   - Favorites
   - Saved searches
   - Recent views
   - Uploads
   - Owners
   - Admin property assignment
   - Observability
   - Schedulers
   - Scripts/data workflows

Do not modify existing application source code.

Completion checks:
- python -c "from app.main import app"
- docs/refactor/openapi_legacy_baseline.json exists
- docs/refactor/ROUTE_INVENTORY.json exists
- docs/refactor/FUNCTIONALITY_COVERAGE_CHECKLIST.md exists
```
