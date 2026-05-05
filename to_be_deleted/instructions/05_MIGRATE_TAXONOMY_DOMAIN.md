# 05 — Migrate Taxonomy Domain

## Goal
Rebuild location taxonomy and property taxonomy in app_refactored and prove parity.

## Cursor Prompt

```md
Migrate taxonomy functionality into app_refactored/domains/taxonomy.

Legacy endpoints:
- GET /api/v1/location-taxonomy
- GET /api/v1/property-taxonomy

Steps:
1. Read legacy routes, services, repositories, schemas.
2. Create refactored taxonomy repository/service/router.
3. Import ORM models only from app/models/.
4. Keep response JSON exactly identical.
5. Add parity tests for both endpoints.
6. Add feature-flag startup routing:
   if settings.use_refactored_taxonomy:
       include app_refactored.domains.taxonomy.router
   else:
       include legacy locations/property_taxonomy routers
7. Default flag must be false.
8. Update FUNCTIONALITY_COVERAGE_CHECKLIST.md for taxonomy.
9. If any legacy behavior is not replicated, add it to MISSING_FUNCTIONALITY_REGISTER.md and do not wire flag.

Completion checks:
- pytest tests/refactor_parity/test_taxonomy_parity.py -q
- pytest tests/smoke/ -q
- python scripts/check_contract_drift.py
```
