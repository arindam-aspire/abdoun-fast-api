## System Architecture Changes – Step-by-Step Refactor Plan

This document translates the validated findings from `FASTAPI_BACKEND_CHANGE_PLANNING_REPORT.md` (Section 1) into an **implementation-ready, linear refactor plan** for the system architecture.  
The goal is to:

- Preserve **existing APIs** (paths, methods, request/response contracts).
- Preserve **behaviour and data semantics**.
- Avoid **unintended side effects** while moving to a clean layered architecture:
  - `API (routers) → Services → Repositories → Database`.

Only after the validation steps pass should corresponding code changes be merged.

---

## 1. End-to-End Step-by-Step Refactor Plan

### Step 1: Inventory Current Behaviour

- List all routers and endpoints that perform DB queries or non-trivial business logic.
- For each endpoint, record:
  - Path and HTTP method.
  - Request/response schema and validation rules.
  - Status codes and error response shapes.

### Step 2: Capture “Before” Behaviour (Tests or Scripts)

- Add or refine:
  - Basic automated tests, or
  - At minimum, manual test scripts (HTTP requests with expected responses).
- Confirm current behaviour for:
  - Successful cases.
  - Typical validation failures.
  - Permission/auth failures (where applicable).

### Step 3: Define Service Layer Contracts

- For each feature area (e.g., users, properties, roles, locations, agents), define service interfaces:
  - `UserService`, `PropertyService`, `RoleService`, etc.
- Express operations in **domain terms**, not HTTP or DB language, e.g.:
  - `create_user`, `update_property_status`, `assign_role_to_user`, etc.
- Specify clear method signatures and return types so that routers can be thin and stable.

### Step 4: Define Repository Interfaces

- For each core entity/aggregate (`User`, `Property`, `Role`, `Location`, `Agent`, etc.), define repository interfaces:
  - `UserRepository`, `PropertyRepository`, `RoleRepository`, etc.
- Describe operations in terms of domain needs, for example:
  - `get_by_id`, `get_by_email`, `list_active`, `search`, `exists`, etc.
- Keep repository interfaces free of FastAPI and HTTP concerns.

### Step 5: Implement Repository Classes

- Create concrete repository classes in `app/repositories/` that:
  - Use the shared SQLAlchemy session/transaction helpers.
  - Encapsulate **all** DB access for their entity/aggregate.
- Move existing SQLAlchemy queries into these repositories:
  - Preserve filters, sorting, pagination, and other query behaviour exactly as-is.
- Ensure transaction behaviour (commit/rollback) remains correct and consistent.

### Step 6: Implement Services on Top of Repositories

- Create service classes in `app/services/` that orchestrate business logic:
  - Inject the required repositories.
  - Implement business rules and cross-entity coordination.
- Move non-trivial business logic out of routers into appropriate service methods:
  - Validation and invariants that go beyond schema validation.
  - Cross-entity checks and workflows.
  - Side effects such as sending emails or events (if any).

### Step 7: Wire Repositories into Services

- Use constructor injection or dependency providers to supply repositories to services.
- Ensure services:
  - Do not open or close DB sessions directly.
  - Do not perform raw SQLAlchemy queries; they call repositories instead.
- Reuse shared transaction helpers to keep commit/rollback semantics clear and consistent.

### Step 8: Refactor Routers to Use Services Only

- For each affected endpoint:
  - Replace in-router DB queries and business logic with a call to the corresponding service method.
  - Keep:
    - Route paths and HTTP methods identical.
    - Request and response schemas unchanged (field names, types, and validation).
    - Status codes and error response shapes the same for all existing scenarios.
- Ensure routers are responsible only for:
  - Request parsing and validation (via Pydantic models and dependencies).
  - Calling services with validated data.
  - Mapping service results to response schemas.

### Step 9: Add FastAPI Dependency Wiring

- Use FastAPI `Depends` to inject service instances into route handlers.
- Ensure:
  - No manual construction of services or repositories in route functions.
  - Dependency graph is explicit and testable.
- Keep dependency wiring in one place where possible (e.g., dependency provider modules).

### Step 10: Add and Extend Repository Tests

- Add unit or integration tests for each repository:
  - CRUD operations.
  - Domain-relevant queries (filters, sorting, pagination).
  - Edge cases (missing records, invalid filters, soft-deleted records where applicable).
- Confirm that repository results match the legacy behaviour from before refactoring.

### Step 11: Add and Extend Service Tests

- Add unit tests for service methods that:
  - Validate business rules and invariants.
  - Confirm correct interaction with repositories (e.g., correct methods called with correct parameters).
- Cover success paths and important error/edge cases.
- Where possible, mock repositories to keep service tests fast and focused.

### Step 12: Add Router Smoke Tests

- Add lightweight tests (or keep a manual test script) for each affected endpoint:
  - Exercise typical success paths.
  - Exercise common error paths (validation failures, not found, unauthorized, etc.).
- Compare results against the “before” behaviour captured in Step 2.
- Ensure:
  - Paths and methods are unchanged.
  - Response payloads and status codes are unchanged for all tested scenarios.

### Step 13: Validate API Compatibility

- Confirm:
  - All route paths and HTTP methods remain unchanged.
  - Request/response schemas remain identical (including field names and types).
  - HTTP status codes and error shapes are unchanged for existing scenarios.
- Use automated tests plus sample requests to verify the contract stability.

### Step 14: Validate Behavioural Compatibility

- Verify that:
  - Service and repository tests show the same input/output behaviour as before for typical and edge cases.
  - Transaction boundaries (timing of commits/rollbacks) are preserved or improved without visible behavioural change.
- Pay special attention to:
  - Error handling and exception translation.
  - Idempotency of operations where relevant.

### Step 15: Validate No Unintended Side Effects

- Confirm that:
  - No new DB queries are added inside routers.
  - No duplicate or unnecessary DB queries are introduced.
  - Logging and error handling are at least as good as before (no silent failures).
  - Performance is not measurably worse for key endpoints.
- If performance changes are observed, profile and adjust repository queries or caching strategies as needed.

### Step 16: Clean Up and Document the Pattern

- Remove any dead or obsolete code left behind in routers or legacy helpers.
- Document the final layering pattern for contributors:
  - Routers → Services → Repositories → DB.
  - Where to add new functionality (which layer and why).
- Keep this document updated as the architecture evolves so it remains the single source of truth for system architecture refactors.

---

## 2. Completion Checklist (Implementation Status)

| Step | Deliverable | Location |
|------|-------------|----------|
| 1 | Inventory of routers, endpoints, schemas, status codes | `docs/architecture/API_INVENTORY.md` |
| 2 | Before behaviour captured in tests and expected contracts | `tests/test_endpoints_contracts.py`, `tests/api_contracts/expected_contracts.py` |
| 3–9 | Service/repository layers, wiring, router refactor | `app/services/`, `app/repositories/`, `app/api/v1/deps/`, `app/api/v1/routes/` |
| 10 | Repository tests | `tests/unit/repositories/test_agent_repository.py` |
| 11 | Service tests (mocked repos) | `tests/unit/services/test_agent_service.py` |
| 12 | Router smoke tests | `tests/test_endpoints_contracts.py` (success, validation, auth failures) |
| 13 | API compatibility (paths, methods, status, response shape) | Same contract tests + `tests/api_contracts/expected_contracts.py` |
| 14 | Behavioural compatibility | Service and repository tests; transaction behaviour in services |
| 15 | No DB in routers | `tests/validation/test_no_db_in_routers.py` |
| 16 | Layering documented, dead code removed | `docs/architecture/LAYERING.md`; agents router refactored (no legacy DB code) |

**Run all checks:** `pytest tests/ -v`

