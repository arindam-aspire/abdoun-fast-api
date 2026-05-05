# 16 — Frontend Impact and API Change Report

## Goal
Produce the exact list of frontend changes needed after refactor/API cleanup.

## Cursor Prompt

```md
Generate frontend impact documentation.

Tasks:
1. Compare openapi_legacy_baseline.json with current OpenAPI for:
   - removed endpoints
   - added endpoints
   - changed response schemas
   - changed auth behavior
2. For every difference, create a row:
   | Endpoint | Type of change | Frontend impact | Required frontend update | Risk |
3. If no contract change is intended, the report must say "No frontend contract change required".
4. If app_refactored keeps the same v1 contracts, mark all frontend impact as NONE.
5. If future v2 APIs are recommended, document them separately under "Future API v2 Suggestions".

Write to docs/refactor/FRONTEND_IMPACT_REPORT.md.

Completion checks:
- docs/refactor/FRONTEND_IMPACT_REPORT.md exists
- python scripts/check_contract_drift.py result is attached/summarized
```
