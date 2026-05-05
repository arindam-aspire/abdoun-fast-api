# 06 — Migrate Properties, Search, Geo Search, and Import Domain

## Goal
Rebuild property discovery behavior without changing frontend contracts.

## Cursor Prompt

```md
Migrate property-related functionality into app_refactored/domains/properties.

Legacy capabilities:
- GET /api/v1/properties
- GET /api/v1/properties/exclusive
- GET /api/v1/properties/{property_id}
- GET /api/v1/properties/{property_id}/similar
- POST /api/v1/properties/geo-search
- POST /api/v1/properties/import-csv

Steps:
1. Inventory legacy request params, aliases, filters, auth behavior, response models, side effects.
2. Implement refactored repository/service/router.
3. Preserve recent-view side effect behavior exactly if legacy route has it.
4. Preserve optional-auth behavior exactly.
5. Preserve import-csv permission behavior exactly.
6. Do not change DB schema.
7. Add parity tests:
   - READ endpoints: status + normalized JSON parity.
   - import-csv: auth/status/shape parity; DB effect only if rollback fixture is reliable.
8. Add startup flag use_refactored_properties, default false.
9. Update coverage checklist.
10. If any filter/sort/alias is missed, add to MISSING_FUNCTIONALITY_REGISTER and do not switch.

Completion checks:
- pytest tests/refactor_parity/test_properties_parity.py -q
- pytest tests/smoke/ -q
- python scripts/check_contract_drift.py
```
