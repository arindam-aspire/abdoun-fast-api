# Frontend Impact Report

## Summary

Refactor work keeps **one** production app (`app.main:app`) and switches implementation via **startup-only** feature flags. Refactored domains that are not yet cut over use the **same** FastAPI `APIRouter` instances as legacy (re-exported from `app_refactored/`), so HTTP methods, paths, and schemas remain aligned with the captured baseline.

**Frontend contract (with all flags `false`, default):** **No frontend contract change required** for paths, methods, or response shapes captured in `docs/refactor/openapi_legacy_baseline.json`.

## Drift check

Latest automated check:

- `python scripts/check_contract_drift.py` → **`no_contract_drift`** (current OpenAPI matches `openapi_legacy_baseline.json` when evaluated in CI/local with default flags).

## Differences when a single refactored flag is `true`

Enabling a flag swaps the **Python import path** for the same router objects (or the dedicated refactored taxonomy router that mirrors legacy). Intended outcome: **no** removed endpoints and **no** schema changes. Any unexpected diff should be treated as a defect and reverted.

## Future API v2 Suggestions

Not in scope for this refactor. Optional future work (separate product decision):

- Versioned `/api/v2/...` for breaking cleanups
- Consolidated pagination / error envelope standards
