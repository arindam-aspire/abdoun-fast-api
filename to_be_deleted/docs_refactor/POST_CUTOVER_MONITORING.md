# Post-Cutover Monitoring

## Logs

- Application log level per environment (`LOG_LEVEL`).
- Spike in `4xx/5xx` after flag changes.
- Auth failures (Cognito / JWT validation messages).

## Metrics

- Request rate and latency (p95/p99) per route if available.
- Prometheus scrape health (`/metrics`).

## Database

- Slow query log / `SLOW_QUERY_THRESHOLD_MS` alerts.
- Connection pool exhaustion.

## User-facing flows

- Login / refresh / logout (especially after `USE_REFACTORED_AUTH`).
- Property search, detail, favorites, submissions (per your product smoke scripts).

## Rollback trigger examples

- Error rate sustained above normal baseline after a flag enable.
- Critical API contract mismatch detected by monitoring or E2E tests.
- Data integrity concerns on write-heavy domains.

Rollback: set the affected `USE_REFACTORED_*` flag(s) to `false`, restart processes, confirm `check_contract_drift` and smoke tests on legacy paths.
