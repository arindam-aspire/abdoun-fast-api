# Testing Approach & Best Practices Verification

This document confirms **which approach** the codebase uses for unit tests and verifies alignment with **industry best practices** for Python FastAPI projects.

---

## 1. Testing Approach Used in This Codebase

### 1.1 Test Layout

| Layer | Location | Purpose |
|-------|----------|---------|
| **Unit** | `tests/unit/` | Isolated tests with mocks; mirrors `app/` structure |
| **API / contract** | `tests/test_endpoints_contracts.py`, `tests/test_security_controls.py` | HTTP behavior, response shape, auth/security |
| **Validation** | `tests/validation/` | Static/architectural checks (e.g. no DB in routers) |
| **Contracts** | `tests/api_contracts/expected_contracts.py` | Centralized expected status codes and response keys |

**Structure under `tests/unit/`:**
- `unit/core/` — auth dependency, config, permissions
- `unit/api/deps/` — dependency injection (get_*_repository, get_*_service)
- `unit/repositories/` — repository tests with mocked `Session`
- `unit/services/` — service tests with mocked repository
- `unit/utils/` — request_context, resilience, logger, security, responses, log_messages
- `unit/observability/` — sentry, tracing, slow_queries
- `unit/test_main.py`, `unit/test_db_session.py`, `unit/test_middleware.py` — app bootstrap, DB, middleware

### 1.2 Concrete Testing Techniques

**A. Unit tests (service / core / utils)**  
- **Approach:** Test one unit in isolation; replace dependencies with **mocks**.
- **Tools:** `pytest`, `unittest.mock.MagicMock`, `pytest.monkeypatch`, `pytest.raises`, `pytest.fixture`.
- **Examples:**
  - **Services:** `AgentService` is constructed with a `MagicMock()` repository; tests set `agent_service._repo.method.return_value = ...` and assert on return values and `HTTPException` (e.g. `tests/unit/services/test_agent_service.py`).
  - **Repositories:** `AgentRepository` / `LocationRepository` receive a mocked `Session`; `session.execute.return_value.scalar_one_or_none.return_value = None` (and similar chains) so no real DB is used (e.g. `tests/unit/repositories/test_agent_repository.py`, `test_location_repository.py`).
  - **Core auth:** `get_current_user` is tested by patching `cognito_service.verify_token` and passing a mock `db`; assertions on `HTTPException` status (401/403) (e.g. `tests/unit/core/test_auth_dependency.py`).
  - **Config:** Helpers like `_get_env_str`, `_parse_csv_env` are tested with `monkeypatch` on `os.environ`; CORS validation is tested via **subprocess** so `Settings()` reads env at import time (e.g. `tests/unit/core/test_config.py`).
  - **Utils:** Pure functions (e.g. `resilience.retry`, `is_retryable_http_error`) are tested with `monkeypatch` for `time.sleep`/`random` and `pytest.mark.parametrize` for branches (e.g. `tests/unit/utils/test_resilience.py`).

**B. API / integration-style tests**  
- **Approach:** Hit real HTTP endpoints with **FastAPI `TestClient`**; optional **dependency overrides** to avoid real external services.
- **Tools:** `TestClient(app)`, `app.dependency_overrides`, shared `client` and `db_available` fixtures in `conftest.py`.
- **Examples:**
  - **Endpoints:** `client.get("/health")`, `client.get("/api/v1/properties?pageSize=2")`; assertions on `status_code` and response keys from `expected_contracts` (e.g. `tests/test_endpoints_contracts.py`).
  - **Security:** Headers (X-Request-ID, X-Content-Type-Options, etc.) and rate limiting (429) are asserted; auth is faked with `app.dependency_overrides[get_auth_service] = lambda: _FakeAuthService()` and restored with `app.dependency_overrides.pop(get_auth_service, None)` (e.g. `tests/test_security_controls.py`).
  - **DB-dependent tests** are skipped when PostgreSQL is unavailable via `pytest.skip` and the `db_available` fixture.

**C. Validation / static tests**  
- **Approach:** Read route file source and assert absence of forbidden patterns (e.g. `get_db`, `Session`, raw SQL).
- **Purpose:** Enforce architecture (no DB access in routers) (e.g. `tests/validation/test_no_db_in_routers.py`).

**D. Fixtures and conftest**  
- **Session-scoped `client`:** Single `TestClient(app)` for API/contract tests.
- **Session-scoped `db_available`:** Probe real DB once to decide whether to run or skip DB-dependent tests.
- **Per-test fixtures:** e.g. `mock_repo`, `agent_service(mock_repo)`, `mock_db`, `mock_session` for unit tests.

---

## 2. Alignment with Industry Best Practices

### 2.1 FastAPI / pytest Best Practices (and how this project follows them)

| Practice | Source / norm | This codebase |
|----------|----------------|----------------|
| **Override dependencies for testing** | FastAPI docs, community guides | ✅ Used in `test_security_controls.py`: `app.dependency_overrides[get_auth_service] = lambda: _FakeAuthService()` and cleanup with `pop`. |
| **Use TestClient for API tests** | FastAPI testing docs | ✅ Used in `test_endpoints_contracts.py`, `test_security_controls.py`; `conftest` provides a shared `client` fixture. |
| **Clean up overrides after test** | Best practice to avoid leakage | ✅ Explicit `try/finally` and `app.dependency_overrides.pop(..., None)` in rate-limit test. |
| **Test at multiple levels** | Test pyramid | ✅ Unit (services, repos, core, utils), API/contract (endpoints, security), validation (architecture). |
| **Mock external and heavy dependencies** | Unit testing best practice | ✅ Repositories mocked in service tests; Cognito and DB mocked in auth dependency tests; `monkeypatch` for time/random/env. |
| **Pytest fixtures for lifecycle** | pytest / FastAPI guides | ✅ `conftest.py` for `client` and `db_available`; per-file fixtures for `mock_session`, `agent_service`, `mock_db`. |
| **Structured test layout** | Project rules (`.cursor/rules/05-testing-observability.mdc`) | ✅ `tests/unit/` with subdirs mirroring `app/`; `tests/validation/`, `tests/api_contracts/`. |
| **Cover success, validation errors, not-found, auth failures** | Rule 05 | ✅ Endpoint tests check 200/403/404/422; service tests check 404/400/409 and auth-related 401/403. |
| **Parametrize for multiple cases** | pytest best practice | ✅ e.g. `test_is_retryable_http_error_filters_by_status_code` with `@pytest.mark.parametrize("status_code,expected", ...)`. |

### 2.2 Gaps or Minor Deviations

| Item | Recommendation | Current state |
|------|----------------|----------------|
| **`tests/integration`** | Rule suggests `tests/unit`, `tests/integration`, `tests/api`. | No dedicated `tests/integration` folder; DB-dependent endpoint tests act as a form of integration test and are skipped when DB is unavailable. |
| **Async tests** | FastAPI is async; some guides use `pytest-asyncio` for async tests. | Async code (e.g. `get_current_user`) is run via `asyncio.run(...)` in sync tests instead of `@pytest.mark.asyncio`; no `pytest-asyncio` dependency. This is valid and keeps the suite simpler. |
| **Fixture scope** | Some guides use a fresh `TestClient` per test to avoid shared state. | Session-scoped `client` is used for speed; dependency overrides are applied and cleared in the specific test that needs them, which is acceptable. |
| **Reference docs** | Rule points to `.ai/fastapi_backend/references/testing.md` and templates. | `.ai/fastapi_backend/` is not present; practice is consistent with the rule’s *described* standards (unit + API + dependency override). |

---

## 3. Summary

**Approach in use:**

1. **Unit tests** — Isolate layers (services, repositories, core, utils) with **mocks** (`MagicMock`, `monkeypatch`); assert return values and raised `HTTPException`; **no real DB or external APIs** in unit tests.
2. **API / contract tests** — Use **TestClient** and optional **dependency overrides** to test HTTP behavior and response shape; skip DB-dependent tests when PostgreSQL is not available.
3. **Validation tests** — Static checks on route source code to enforce architecture (e.g. no DB in routers).
4. **Centralized contracts** — `expected_contracts.py` for status codes and response keys to keep API tests consistent.

**Verdict:** This approach **matches common industry best practices** for Python FastAPI projects: layered tests, dependency overrides for controllability and speed, pytest fixtures, mocks for isolation, and a clear split between unit, API, and validation tests. The main structural difference is the absence of a dedicated `tests/integration` directory; the intent of integration-style coverage is partially met by the DB-dependent API tests and by the architectural validation tests.
