# Single-package migration checkpoints (`app_refactored` → `app.domains`)

## Goal

One Python application package (`app`) only. Domain routers and taxonomy implementation now live under **`app.domains`**. The old top-level **`app_refactored`** package was removed after the move.

## Checkpoints (for git history)

Use these as commit titles or tags when replaying the migration:

1. **Checkpoint A — Add `app/domains` tree**  
   Copy former `app_refactored/domains/*`, `core/`, `shared/`, plus optional placeholder packages. Fix imports to `app.domains.*` (avoid `app.domains.domains` after naive replace).

2. **Checkpoint B — Wire router**  
   Update `app/api/v1/router.py` to import from `app.domains` instead of `app_refactored.domains`.

3. **Checkpoint C — Tests**  
   Update `tests/refactor_parity/*` imports to `app.domains`.

4. **Checkpoint D — Remove `app_refactored`**  
   Delete the `app_refactored/` directory; confirm `rg app_refactored` only hits `to_be_deleted/` (archived docs).

5. **Checkpoint E — Verify**  
   - `python -c "from app.main import app"`  
   - `pytest tests/smoke/ tests/refactor_parity/ -q`  
   - `pytest tests/ -q`

## Layout after migration

```
app/
  api/              # FastAPI routers, v1 composition
  core/             # settings, limiter, etc.
  domains/          # feature-flagged domain entrypoints + taxonomy implementation
    taxonomy/
    properties/
    personalization/
    ...
    core/           # small domain primitives (result, errors) — not app.core.config
    shared/
  models/
  services/
  repositories/
  ...
```

## Note

`app.core` (config) and `app.domains.core` (domain primitives) are **different** packages; both names are valid.
