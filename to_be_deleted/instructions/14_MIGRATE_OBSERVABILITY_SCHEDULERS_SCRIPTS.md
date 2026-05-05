# 14 — Migrate/Validate Observability, Schedulers, and Scripts

## Goal
Ensure non-API functionality is not missed.

## Cursor Prompt

```md
Audit and validate non-API functionality.

Areas:
- request ID middleware
- security headers
- CORS
- Prometheus metrics
- OpenTelemetry
- Sentry
- slow query tooling
- dashboard summary scheduler
- S3 utilities
- media URL signer
- scripts: seed, RBAC verify, CSV import, backfills, translations, pricing/features/reference-number updates

Rules:
1. Do not rewrite operational scripts unless needed.
2. Create docs/refactor/NON_API_FUNCTIONALITY_AUDIT.md.
3. For each item, mark:
   - legacy location
   - whether app_refactored depends on it
   - whether unchanged/shared/migrated
   - test or verification command
4. Add smoke tests for middleware/health/metrics where possible.
5. If any non-API behavior may be broken by refactored routes, add to MISSING_FUNCTIONALITY_REGISTER.

Completion checks:
- docs/refactor/NON_API_FUNCTIONALITY_AUDIT.md complete
- pytest tests/smoke/ -q
- python -c "from app.main import app"
```
