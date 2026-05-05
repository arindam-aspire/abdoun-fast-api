# Refactor Implementation Standards

This document defines the target implementation standards to apply during refactoring, based on inconsistencies found in `docs/refactor/IMPLEMENTATION_CONSISTENCY_AUDIT.md`.

## 1) Pagination Standard

- Current inconsistent patterns found:
  - `page + pageSize`
  - `page + limit`
  - `limit + offset`
  - nested `pagination` objects
  - list endpoints with no pagination metadata
- New preferred pattern:
  - Request: `page` (1-based), `pageSize` (max controlled centrally)
  - Internal: convert to `offset = (page - 1) * page_size`
  - Response: `items`, `total`, `page`, `pageSize`
- Example code pattern:
```python
class PageParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100, alias="pageSize")

offset = (params.page - 1) * params.page_size
rows, total = repo.list_items(limit=params.page_size, offset=offset)
return create_success_response(
    data={"items": rows, "total": total, "page": params.page, "pageSize": params.page_size}
)
```
- Where this standard applies:
  - All list/search endpoints across users, agents, properties, submissions, owners.
- Exceptions allowed:
  - High-volume internal batch endpoints documented as internal-only.

## 2) DB Access Standard

- Current inconsistent patterns found:
  - Repository-based access and direct Session access mixed.
  - Services sometimes instantiate repository internally with raw Session.
- New preferred pattern:
  - Route -> Service -> Repository only for request handling.
  - No route-level DB queries.
  - Services receive repositories through DI, not Session.
- Example code pattern:
```python
def get_user_service(repo: UserRepository = Depends(get_user_repository)) -> UserService:
    return UserService(repo)
```
- Where this standard applies:
  - `app/api/v1/routes`, `app/services`, `app/api/v1/deps`.
- Exceptions allowed:
  - Auth dependency read path (`get_current_user`) and documented scheduler/import pipelines.

## 3) Transaction Standard

- Current inconsistent patterns found:
  - `repo.commit()/rollback()` in many services.
  - direct `db.commit()/rollback()` in import helpers.
  - mixed multi-step transaction boundaries.
- New preferred pattern:
  - Service owns one unit-of-work boundary per request workflow.
  - Repository methods do not auto-commit.
- Example code pattern:
```python
try:
    repo.create(entity)
    repo.update_related(...)
    repo.commit()
except Exception:
    repo.rollback()
    raise
```
- Where this standard applies:
  - All write operations in services.
- Exceptions allowed:
  - Explicitly documented fire-and-forget side effects (no transaction coupling).

## 4) Response Envelope Standard

- Current inconsistent patterns found:
  - `StandardResponse[T]` mixed with raw Pydantic and raw dict responses.
- New preferred pattern:
  - Default: `StandardResponse[T]`.
  - Explicit allow-list for raw responses (if contractually required).
- Example code pattern:
```python
@router.get("", response_model=StandardResponse[UsersListPaginatedResponse])
def list_users(...):
    payload = UsersListPaginatedResponse(...)
    return create_success_response(data=payload, message=None)
```
- Where this standard applies:
  - All public API endpoints.
- Exceptions allowed:
  - Endpoints explicitly marked as raw contract endpoints in API spec.

## 5) Auth/Permission Standard

- Current inconsistent patterns found:
  - Mixed use of `get_current_user`, `require_role`, `require_permission`.
  - Sensitive routes with unclear enforcement (`/owners`).
- New preferred pattern:
  - Every endpoint declares one of: public, authenticated, role-gated, permission-gated.
  - Sensitive write endpoints require explicit permission check.
- Example code pattern:
```python
@router.post("", dependencies=[require_permission(UserPermissions.OWNER_MANAGE)])
def create_owner(current_user: Annotated[User, Depends(get_current_user)], ...):
    ...
```
- Where this standard applies:
  - All routes, especially admin/agent/owners/uploads/submissions/import.
- Exceptions allowed:
  - Public token endpoints with strict scoped token validation.

## 6) Error Handling Standard

- Current inconsistent patterns found:
  - Broad `except Exception` wrappers and inconsistent error messages.
- New preferred pattern:
  - Repository raises typed domain errors or lets DB errors bubble.
  - Service maps to domain exceptions.
  - Route/service boundary maps domain exceptions to `HTTPException`.
- Example code pattern:
```python
try:
    service.run(...)
except DomainNotFoundError as exc:
    raise HTTPException(status_code=404, detail=str(exc))
except DomainValidationError as exc:
    raise HTTPException(status_code=400, detail=exc.errors)
```
- Where this standard applies:
  - All services and route handlers.
- Exceptions allowed:
  - Defensive non-blocking side effects with warning logs.

## 7) Naming Standard

- Current inconsistent patterns found:
  - `agent.py` vs `agents.py`, `page_size`/`pageSize`/`limit`, sort alias variants.
- New preferred pattern:
  - Route modules named by scope (`*_admin_routes.py`, `*_public_routes.py`).
  - External API uses camelCase aliases only when needed.
  - Internal Python names use snake_case.
- Example code pattern:
```python
page_size: int = Query(20, alias="pageSize", ge=1, le=100)
sort_by: str = Query("createdAt", alias="sortBy")
```
- Where this standard applies:
  - Routes, schemas, service function signatures, repository methods.
- Exceptions allowed:
  - Temporary backward-compat aliases with deprecation metadata and deadline.

## 8) Soft Delete Standard

- Current inconsistent patterns found:
  - Some domains soft-delete; some hard-delete (`owners` domain).
- New preferred pattern:
  - Business entities use `deleted_at`, `deleted_by`.
  - Read queries default to `deleted_at IS NULL`.
  - Include-deleted requires explicit flag.
- Example code pattern:
```python
def get_by_id(id: UUID, include_deleted: bool = False):
    stmt = select(Model).where(Model.id == id)
    if not include_deleted:
        stmt = stmt.where(Model.deleted_at.is_(None))
```
- Where this standard applies:
  - Users, agents, properties, submissions, owners (if adopted).
- Exceptions allowed:
  - Join tables or purely technical tables explicitly marked hard-delete.

## 9) Search/Filter/Sort Standard

- Current inconsistent patterns found:
  - Different parameter names and sort semantics per endpoint.
- New preferred pattern:
  - Shared query schema format: `search`, typed filters, `sortBy`, `sortOrder`, `page`, `pageSize`.
  - Sort allow-list per endpoint/domain.
- Example code pattern:
```python
ALLOWED_SORT = {"createdAt": Model.created_at, "name": Model.name}
order_col = ALLOWED_SORT.get(sort_by, Model.created_at)
stmt = stmt.order_by(order_col.desc() if sort_order == "desc" else order_col.asc())
```
- Where this standard applies:
  - All list/search endpoints.
- Exceptions allowed:
  - Endpoints where order must always be deterministic fixed sort for business reasons.

## 10) Schema Validation Standard

- Current inconsistent patterns found:
  - Large mixed schema modules, raw dict responses, alias-heavy payloads.
- New preferred pattern:
  - Separate request and response schemas by bounded context.
  - Avoid exposing internal fields.
  - Use validators for cross-field constraints.
- Example code pattern:
```python
class SubmissionRequest(BaseModel):
    city_id: int
    area_id: int

    @model_validator(mode="after")
    def validate_location(self):
        if self.area_id <= 0 or self.city_id <= 0:
            raise ValueError("Invalid location ids")
        return self
```
- Where this standard applies:
  - `app/schemas/*` and route contracts.
- Exceptions allowed:
  - Thin pass-through integration payloads with explicit documentation.

## 11) Logging/Observability Standard

- Current inconsistent patterns found:
  - Uneven logging depth, limited standardized metrics usage.
- New preferred pattern:
  - Structured logs with request_id, endpoint, user_id (if available), outcome, latency.
  - Error logs include stable error code.
  - Metrics for request count/error rate/DB latency on critical flows.
- Example code pattern:
```python
api_logger.info("user.update.success", extra={"request_id": rid, "user_id": str(user.id)})
```
- Where this standard applies:
  - Routes, services, scheduler jobs.
- Exceptions allowed:
  - Utility-level pure functions with no side effects.

## 12) Background Task Standard

- Current inconsistent patterns found:
  - Scheduler and import paths use direct SQL/session patterns unlike request stack.
- New preferred pattern:
  - Background jobs use dedicated repository layer or job data access module.
  - Explicit transaction and retry boundaries.
  - Clear idempotency and failure logging.
- Example code pattern:
```python
def run_job(session_factory):
    db = session_factory()
    try:
        rows = repo.fetch_pending(db)
        repo.process(db, rows)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```
- Where this standard applies:
  - Schedulers, importers, asynchronous task handlers.
- Exceptions allowed:
  - Single-statement maintenance jobs with explicit operational runbook.

