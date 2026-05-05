# 17 — Missing Functionality Audit and Gap Closure

## Goal
Force Cursor to prove nothing was missed before final cutover.

## Cursor Prompt

```md
Run a full missing-functionality audit.

Inputs:
- docs/refactor/FUNCTIONALITY_COVERAGE_CHECKLIST.md
- docs/refactor/ROUTE_INVENTORY.json
- docs/refactor/NON_API_FUNCTIONALITY_AUDIT.md
- docs/refactor/MISSING_FUNCTIONALITY_REGISTER.md
- all tests/refactor_parity/

Tasks:
1. For every legacy endpoint, confirm one of:
   - migrated and parity-tested
   - intentionally legacy/shared
   - intentionally deferred with reason
2. For every service in app/services/, confirm one of:
   - migrated
   - still shared
   - not needed with reason
3. For every script/scheduler/middleware, confirm no breakage.
4. Generate docs/refactor/FINAL_FUNCTIONALITY_PARITY_REPORT.md.
5. If any item is missing or uncertain, mark BLOCKING and do not proceed to Task 18.

Completion checks:
- FINAL_FUNCTIONALITY_PARITY_REPORT.md has zero BLOCKING items
- MISSING_FUNCTIONALITY_REGISTER.md has zero unresolved critical items
- pytest tests/refactor_parity/ -q
- pytest tests/smoke/ -q
```
