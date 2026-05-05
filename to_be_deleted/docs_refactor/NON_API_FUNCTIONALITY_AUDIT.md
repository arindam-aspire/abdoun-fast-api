# Non-API Functionality Audit

Operational and cross-cutting behavior outside individual v1 route handlers. Refactored domains reuse legacy routers and shared `app/` infrastructure, so these remain **shared / unchanged** unless noted.

| Item | Legacy location | `app_refactored` dependency | Status | Verification |
|------|-----------------|-----------------------------|--------|----------------|
| Request ID middleware | `app/middleware/request_id.py`, mounted in `app/main.py` | None (global app) | Shared | `pytest tests/unit/test_middleware.py` (if present); manual `curl -H "X-Request-ID: test" /health` |
| Security headers | `app/middleware/security.py` | Shared | Shared | `pytest tests/test_security_controls.py` |
| CORS | `app/main.py` + `app/core/config.py` | Shared | Shared | Config / integration |
| Prometheus metrics | `app/middleware/metrics.py`, `app/main.py` | Shared | Shared | `GET /metrics` when `METRICS_ENABLED` |
| OpenTelemetry | `app/observability/tracing.py`, `app/main.py` | Shared | Shared | Env `OTEL_ENABLED` |
| Sentry | `app/observability/sentry.py`, `app/main.py` | Shared | Shared | Env `SENTRY_ENABLED` |
| Slow query logging | `app/db/session.py` | Shared | Shared | `SLOW_QUERY_THRESHOLD_MS` |
| Dashboard summary scheduler | `app/schedulers/dashboard_summary_scheduler.py`, lifespan in `app/main.py` | Shared | Shared | Env `DASHBOARD_SUMMARY_SCHEDULER_ENABLED` |
| S3 / presign utilities | `app/services/s3_service.py`, `app/services/upload_service.py`, `app/services/media_url_signer.py` | Used by legacy services behind refactored re-exports | Shared | Unit tests under `tests/unit/services/` |
| Seed / RBAC / import scripts | `scripts/` (e.g. `seed_rbac.py`, `import_from_csv.py`, `verify_rbac.py`) | Not part of `app_refactored` | Unchanged | Run scripts in non-prod as documented in repo |

**Conclusion:** Refactored route modules do not replace middleware, DB session, or observability stacks. No non-API regressions are introduced by router re-exports alone.
