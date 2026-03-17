# Test coverage and reaching 100%

Current coverage is **59%**. To reach **100%** (required by `[tool.coverage.report] fail_under = 100`), add unit tests for every missing line reported by:

```bash
pytest --cov=app --cov-report=term-missing
```

## Modules still needing tests (Missing lines)

- **app/db/session.py** — 30-31, 34-40 (otel/slow_queries at import; test via import under mocks or integration)
- **app/middleware/request_id.py** — 33-34 (opentelemetry span; mock `get_current_span`)
- **app/observability/slow_queries.py** — 35 (branch: `if not start_times`)
- **app/api/v1/routes/agents.py** — 68 lines (agent CRUD; use TestClient + dependency_overrides)
- **app/api/v1/routes/auth.py** — 17 lines
- **app/api/v1/routes/properties.py** — 1 line
- **app/api/v1/routes/search.py** — 2 lines
- **app/api/v1/routes/users.py** — 16 lines
- **app/repositories/** — agent (43), auth (26), location (2), property (86), user (27) — mock `Session` and assert calls/return values
- **app/services/** — agent (364), auth (207), cognito (221), csv_importer (246), geo_search (2), notification (5), property_import (1), property_search (16), translation (97), user (57) — mock repos and external APIs
- **app/schemas/property.py** — 300 lines (validators; instantiate models with various payloads)
- **app/schemas/user.py** — 83 lines

## Strategy

1. **Repositories**: In `tests/unit/repositories/`, add tests that pass a `MagicMock()` session, stub `execute().scalar_one_or_none().return_value` etc., and call each repo method.
2. **Services**: In `tests/unit/services/`, mock the repository and external clients (Cognito, boto3, etc.), then call service methods and assert outcomes and raised exceptions.
3. **Routes**: Use `TestClient(app)` with `app.dependency_overrides` to inject fake auth/service; `GET`/`POST` each endpoint and assert status and response shape.
4. **Schemas**: For each Pydantic model/validator, construct instances with the payloads that hit missing branches (see `term-missing` for line numbers).

Once every file shows `100%` in the report, `pytest --cov=app` will pass with `fail_under = 100`.
