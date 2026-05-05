# Implementation Consistency Audit

## Executive Summary

This audit reviews consistency in the FastAPI + SQLAlchemy implementation without changing runtime behavior. The codebase is generally layered (route -> deps -> service -> repository), but there are multiple parallel patterns for the same responsibilities.

Most important findings:
- Pagination is implemented in at least 5 distinct styles.
- Database access is mostly repository-based, but several services still use direct `Session` operations.
- Transaction boundaries are inconsistent (service-owned repo commits vs direct service/session commits).
- Response format is mixed (`StandardResponse[T]`, raw models, raw `dict`, and endpoints with no `response_model`).
- Auth and permission checks are inconsistent across sensitive domains (`/owners`, import/upload/admin-agent flows).

## Top 10 Consistency Problems

1. Multiple pagination contracts (`page/pageSize`, `page/limit`, `limit/offset`, nested `pagination`, and implicit no-meta list endpoints).  
2. Split DB access style: repositories are standard, but direct DB calls still exist in services/importers/scheduler.  
3. Mixed transaction ownership (repository commit wrappers, direct `db.commit()`, mixed multi-repo writes).  
4. Response envelope inconsistency (some routes return `StandardResponse`, others return raw models/dicts).  
5. Mixed auth dependency style (`Depends(get_current_user)`, `require_role`, `require_permission`, and public routes in same module).  
6. Naming inconsistency (`agent.py` and `agents.py`, `page_size` + `pageSize`, `limit` meaning period in one endpoint).  
7. Timestamp consistency issues (`datetime.now()` naive and timezone-aware usage mixed).  
8. Soft delete implementation differs by domain (full soft delete in user/submission/property, hard delete in owner mappings).  
9. Error handling inconsistency (`HTTPException` everywhere, but broad `except Exception` and varied message contracts).  
10. Cross-cutting observability patterns are uneven (rate limiting only some routes, mixed logging depth, scheduler-specific patterns).

## Risk Ranking

### High
- Auth/permission inconsistency on sensitive endpoints.
- Mixed transaction patterns for multi-step write flows.
- Soft delete and deleted-record filtering divergence across domains.
- Timestamp naive vs aware usage in security-sensitive/admin workflows.

### Medium
- Pagination + response metadata drift across APIs.
- Error contract inconsistency and generic exception wrappers.
- Naming and alias compatibility debt causing future API drift.

### Low
- File/module size imbalance and duplicated compatibility endpoints.
- Cross-cutting observability style differences.

## 1) Pagination Consistency

Observed pagination styles: **5**
1. `page + pageSize` (`alias="pageSize"`) with `total/page/pageSize`
2. `page + limit` with `total/page/limit`
3. `limit + offset` only
4. nested `pagination: {page, limit, totalItems, totalPages}`
5. non-paginated list endpoints returning all records with `total=len(items)`

| File | Function | Layer | Pagination style | Response metadata | Issue | Recommended standard |
|---|---|---|---|---|---|---|
| `app/api/v1/routes/properties.py` | `list_properties` | Route | `page` + `pageSize` alias | `total`, `page`, `pageSize` | Different from `limit/offset` routes | Standardize to `page` + `pageSize` externally |
| `app/api/v1/routes/users.py` | `list_users` | Route | `page` + `pageSize` alias | `total`, `page`, `pageSize` | Good pattern but not universal | Use as canonical external contract |
| `app/api/v1/routes/agent_properties.py` | `list_agent_properties` | Route/Service | `page` + `limit` | `total`, `page`, `limit` | Naming differs from properties/users | Rename externally to `pageSize` (compat alias allowed) |
| `app/api/v1/routes/owners.py` | `list_owners` | Route/Service | `limit` + `offset` | none beyond list data | Not aligned with 1-based API pagination | Replace with page-based contract |
| `app/api/v1/routes/admin.py` | `get_admin_property_performance` | Route/Service | `page` + `pageSize` + compat alias on `limit` for period | nested `pagination` object | `limit` overloaded for period compatibility | Remove overloaded alias in v2; keep explicit `period` |
| `app/api/v1/routes/agents.py` | `list_agents` | Route/Service | `page` + `pageSize` + `limit` compat + sort aliases | nested `pagination` object | High compatibility burden in one route | Keep one public pattern; deprecate old aliases with deadline |
| `app/services/property_submission_service.py` | `list_my_draft_submissions` | Service | manual slice after fixed fetch (`limit=200`) | dict with `items,total,page,limit` | Pagination partly done in service memory | Move all pagination/count to repository query |

## 2) Database Access Consistency

Observed DB access styles: **4**
1. Repository ORM/Core query (dominant)
2. Service-level direct `Session` operations
3. Raw SQL via `text()` in repositories/scheduler
4. Helper/core dependencies reading DB directly (`auth`, `permissions`)

| File | Function | Layer | DB access style | Transaction owner | Issue | Recommended standard |
|---|---|---|---|---|---|---|
| `app/repositories/property_repository.py` | `search_properties` | Repository | ORM/Core `select/func/join` | Service caller | Consistent with repository pattern | Keep |
| `app/repositories/admin_dashboard_repository.py` | multiple | Repository | Raw SQL `text()` analytics | Service caller | Heavy SQL strings mixed with app logic | Keep raw SQL only for analytics, document rationale |
| `app/services/property_search_service.py` | constructor and methods | Service | Instantiates repository with direct `db` | N/A reads | Service knows Session directly | Inject repository via deps for uniformity |
| `app/services/property_import_service.py` | `import_from_csv` | Service | Direct `Session` passed to importer | Service/direct session | Bypasses repository boundary | Introduce import repository/unit-of-work facade |
| `app/services/csv_importer.py` | multiple | Service/helper | Direct `db.execute/add/commit/rollback` | Service | Significant divergence from standard service-repo flow | Move write/query logic into repositories |
| `app/core/auth.py` | `get_current_user` | Core dependency | Direct DB `select(User)` | Dependency scope | Security dependency contains DB query | Acceptable, but enforce read-only + documented exception |

Routes directly using DB/session: **none found in `app/api/v1/routes`** by static search.

## 3) Dependency Injection Consistency

| Route file | Dependency | Pattern used | Consistent? | Issue | Recommendation |
|---|---|---|---|---|---|
| `app/api/v1/deps/agents.py` | `get_agent_service` | `repo -> service` factory chain | Yes | Good | Use as baseline |
| `app/api/v1/deps/auth.py` | `get_profile_update_service` | Manual service construction with two repos | Partial | Multi-repo service bypasses typed alias pattern used elsewhere | Keep but standardize dependency typing style |
| `app/api/v1/deps/properties.py` | `get_property_search_service` | Service built with raw `db` and signer | No | Service self-constructs repository internally | Inject repository in deps |
| `app/api/v1/deps/search.py` | `get_property_import_service` | Service built with raw `db` only | No | Skips repository abstraction | Add import repository/facade |
| `app/api/v1/routes/users.py` | route dependencies | mixes `Depends(get_current_user)` + `dependencies=[require_permission(...)]` | Partial | Two authorization styles in same route | Standardize to explicit typed user + permission dependency |
| `app/api/v1/routes/agents.py` | route dependencies | `require_role(...)` + `Depends(service)` | Yes | Public and admin endpoints mixed in one module | Split router by auth surface |

## 4) Response Format Consistency

| Endpoint | response_model | Actual return | Envelope style | Issue | Recommendation |
|---|---|---|---|---|---|
| `/properties` | none | `PropertySearchResponse` | raw model | Not wrapped in `StandardResponse` unlike most API | Pick one API-wide envelope policy |
| `/properties/geo-search` | none | `PropertyListResponse` | raw model | Same divergence | Align with selected policy |
| `/location-taxonomy` | none | `dict` | plain dict | No schema envelope and weak contract | Add typed response schema |
| `/property-taxonomy` | none | `dict` | plain dict | Same | Add typed response schema |
| Most CRUD routes | `StandardResponse[T]` | `create_success_response(...)` | standard envelope | Good, but mixed with raw routes | Keep as default |
| `/properties/import-csv` | `ImportResponse` | raw model | domain-specific | Acceptable exception but undocumented | Document explicit envelope exception |

## 5) Error Handling Consistency

| File | Function | Error pattern | Issue | Recommended standard |
|---|---|---|---|---|
| `app/services/owner_service.py` | multiple | broad `except Exception` -> generic `HTTPException` | Loses root cause and category | Catch domain-specific DB errors first, generic last |
| `app/services/property_submission_service.py` | multiple | many explicit `HTTPException` + broad catch wrappers | Very large mixed error style | Centralize domain exception mapping |
| `app/services/auth_service.py` | multiple | deep nested broad catches | Hard to reason about error contract | Introduce service-specific exception classes |
| `app/api/v1/routes/properties.py` | `get_property` | swallow tracking error and log warning | Intentional non-blocking side effect | Keep, but document as approved exception |
| `app/services/favorite_service.py` | multiple | repo rollback then rethrow HTTPException | Mostly consistent | Standardize message/error codes across services |

## 6) Auth and Permission Consistency

| Endpoint | Auth style | Expected sensitivity | Issue | Recommendation |
|---|---|---|---|---|
| `/owners/*` | no auth dependency on routes | High | Owner PII endpoints appear public | Require admin/authorized role and explicit permission |
| `/properties/import-csv` | `require_permission(PROPERTY_CREATE)` + `get_current_user` | High | Good protection | Keep |
| `/uploads/presigned-url` | authenticated user only | High | No fine-grained permission check | Add permission or submission ownership policy check |
| `/agents/invite/validate` and `/agents/onboarding` compat | public | Medium/High | Public token-based endpoints in admin-heavy module | Split to dedicated public onboarding router |
| `/admin/*` | `require_role(ADMIN)` | High | Consistent | Keep |
| `/agent/property-performance` | `require_role(AGENT)` | Medium | Consistent | Keep |
| `/property-submissions/*` | authenticated user | High | Good baseline; admin moderation separated | Keep, add explicit submission ownership assertions docs |

Needs manual verification:
- Whether upstream gateway/WAF enforces additional auth on `/owners`.

## 7) Naming Consistency

| Area | Current names | Issue | Recommended naming |
|---|---|---|---|
| Route modules | `agent.py` and `agents.py` | Singular/plural split by behavior not obvious | Use explicit names (`agent_dashboard_routes.py`, `agent_admin_routes.py`) |
| Pagination params | `page_size`, `pageSize`, `limit`, `offset` | Multiple dialects | External: `page`, `pageSize`; internal: `page`, `page_size` |
| Compat params | `sortBy`, `sort_by`, `order`, `sortOrder` | Aliases accumulate tech debt | Keep one canonical + scheduled deprecation |
| Domain terms | `properties_normalized` (table) vs `PropertyNormalized`/`Property` | Alias confusion in repository/service code | Use one model alias project-wide |
| Location terms | `location_id` vs `area_id` | Mixed semantics in schemas/services | Normalize on one canonical term per domain |

## 8) Timestamp and Audit Field Consistency

| Table/model | Audit fields | Missing/inconsistent fields | Recommendation |
|---|---|---|---|
| `User` | `created_at`, `updated_at`, `deleted_at`, `deleted_by` | Good | Use as audit baseline |
| `PropertyListingSubmission` | includes soft delete + submit/review timestamps | Good, but service-level writes vary | Keep; centralize timestamp helper |
| `PropertyNormalized` | `created_at`, `updated_at`, `created_by`, `deleted_at`, `deleted_by` | `updated_by` named as `updated_by_user_id` | Normalize naming (`updated_by`) |
| `AgentProfile` | lifecycle fields, delete fields | service uses naive `datetime.now()` in places | Enforce timezone-aware UTC writes |
| services (`agent_service`, `user_service`) | mixed `datetime.now()` and `datetime.now(timezone.utc)` | Naive/aware mix | Use one utility `utc_now()` |

## 9) Soft Delete Consistency

| Domain | Delete style | Filter style | Issue | Recommendation |
|---|---|---|---|---|
| Users | Soft delete (`deleted_at/deleted_by/is_active=false`) | Repositories filter `deleted_at IS NULL` | Consistent | Keep |
| Property submissions | Soft delete in service and repository filtering | Usually excludes deleted unless flag set | Consistent with optional include | Keep |
| Properties | Soft delete and filters in repository | List/detail usually exclude deleted | Consistent | Keep |
| Agents (`AgentProfile`) | Soft delete fields used | Filtering present, but timestamp naive in service | timezone inconsistency | UTC-aware soft-delete writes |
| Owners / mappings | Hard delete | no soft-delete fields | Diverges from other business entities | Decide explicit policy: hard-delete by design or add soft-delete |

## 10) Search/Filter/Sort Consistency

| Endpoint | Filter style | Sort style | Search style | Issue | Recommendation |
|---|---|---|---|---|---|
| `/properties` | many query aliases, textual filters + budget mapping | fixed `created_at desc` | no free-text global search | Sort is implicit/non-configurable | Add explicit sort contract with allowlist |
| `/agents` | `status/search/period` | `sortBy/sortOrder` + compat aliases | `ilike` on name/email | Heavy alias compatibility burden | Keep one canonical sort/filter format |
| `/users` | role/userType/is_active/period/search | fixed order by created | `ilike` on email/name/phone | Filter naming differs from agents/properties | Unify filter naming and period enum |
| `/owners` | pagination only | fixed created desc | none | Minimal filtering, non-standard pagination | Align with standard list query contract |

## 11) Schema Validation Consistency

| Schema | Concern | Issue | Recommendation |
|---|---|---|---|
| `app/schemas/property.py` | size/complexity | very large schema module | Split by request/response/domain segments |
| `app/schemas/user.py` | mixed API + admin + dashboard payloads | broad responsibility | Split by bounded context |
| multiple routes returning `dict` | weak typing | no strict response schema | Introduce explicit Pydantic response models |
| alias-heavy query/schema fields | frontend compatibility mixed in core schema | alias debt can hide canonical shape | enforce canonical fields + alias deprecation policy |

## 12) Service/Repository Boundary Consistency

| Domain | Current boundary | Issue | Recommended split |
|---|---|---|---|
| Property search | Service creates repository internally from Session | boundary leak (service knows persistence type) | Inject repository only |
| CSV import | Import service/helper uses direct Session + SQLAlchemy ops | bypasses repository/UoW | Introduce import repository layer |
| Auth/Profile update | service coordinates multiple repos directly | acceptable orchestration but inconsistent DI style | Keep orchestration in service, standardize constructor dependency style |
| Dashboard analytics | service delegates read SQL to repository | clean separation | Keep |

## 13) File/Module Size and Responsibility

| File/Class/Function | Size/Complexity signal | Responsibility issue | Refactor recommendation |
|---|---|---|---|
| `app/schemas/property.py` | ~1522 lines | many schema concerns combined | split by domain slices |
| `app/services/property_submission_service.py` | ~1504 lines | workflow orchestration + validation + mapping + transaction | break into workflow + validators + mappers |
| `app/services/agent_service.py` | ~1230 lines | invite/onboard/admin lifecycle + assignments | split into invite, lifecycle, assignment services |
| `app/services/normalized_importer.py` | ~932 lines | import ETL + taxonomy upsert + commit logic | separate ETL stages and repository helpers |
| `app/api/v1/routes/agents.py` | ~517 lines | admin, public compat, assignment endpoints together | split by auth/surface area |

## 14) Cross-Cutting Behavior Consistency

| Concern | Current patterns | Issue | Recommended standard |
|---|---|---|---|
| Logging | route/service/repository logging; message constants used | depth and granularity vary widely | define structured logging policy by layer |
| Request IDs | not consistently visible in route/service logs | hard traceability | enforce request-id in log context middleware |
| Metrics | `app/observability/metrics.py` exists; limited visible usage | uneven instrumentation | standard endpoint + DB operation metric hooks |
| Background tasks/scheduler | scheduler uses direct session and SQL text | pattern differs from request path repositories | keep scheduler pattern but document exceptions |
| S3/media signing | centralized `MediaUrlSigner` in some flows | not uniformly applied to all media-returning DTOs | enforce signer step in response assembly helpers |
| Rate limiting | applied on auth endpoints only | uneven abuse protection for sensitive write endpoints | define policy by endpoint class |
| Config access | mostly via `get_settings()`, but direct reads in services | mostly consistent | keep and avoid ad-hoc env access |

## Recommended Standard Patterns

- **API pagination:** external `page` (1-based) + `pageSize`; response `items,total,page,pageSize`.
- **DB access:** no route-level DB; services depend on repositories, not `Session`.
- **Transactions:** service is unit-of-work owner; one commit/rollback boundary per request workflow.
- **Response envelope:** choose one default (`StandardResponse[T]`) and explicitly document exceptions.
- **Auth/permission:** explicit dependency per endpoint sensitivity; avoid mixed public/admin routes in one module.
- **Errors:** domain exceptions in service/repo mapped to HTTP at route/service boundary consistently.
- **Soft delete:** consistent semantics and filtering contracts for all business entities.
- **Time:** UTC-aware timestamps everywhere for writes and comparisons.

## Refactor Task Suggestions

1. Introduce a shared pagination contract package (query schema + response schema + helpers).  
2. Move direct DB session usage from import/search services into repository or UoW adapters.  
3. Split `agents` module into public onboarding vs admin management routers/services.  
4. Normalize auth enforcement for `/owners` and upload/submission-sensitive endpoints.  
5. Create a project-wide timestamp utility and replace naive `datetime.now()` usage.  
6. Define a formal exception hierarchy and error mapping matrix.  
7. Break oversized service/schema files into bounded modules before behavior refactors.  
8. Publish compatibility/deprecation policy for query aliases (`limit`, `sort_by`, `order`).

## Do Not Change Yet (Coordination Required)

- Public API parameter aliases currently used by frontend (`pageSize`, `limit`, `sortBy`, `sortOrder`, etc.).
- Response envelope behavior on `/properties`, `/geo-search`, taxonomy endpoints (frontend contract impact).
- Soft-delete vs hard-delete choice for owners and owner-property mappings (data governance + migration implications).
- Admin/agent endpoint split that may affect route paths and client integrations.
- Any timestamp column type/naming standardization requiring DB migration.

## Missing Information / Uncertain Findings

- `/owners` auth may be enforced outside app (gateway/reverse proxy). **Needs manual verification.**
- Feature-flagged domain routers (`use_refactored_*`) may introduce alternate patterns not audited in active path. **Needs manual verification.**
- Some scripts/schedulers use direct DB by design; operational constraints may justify exceptions. **Needs manual verification.**

## Consistency Standards Checklist For Refactor

- [ ] One pagination request/response contract used across all list endpoints.
- [ ] No route contains direct DB access.
- [ ] Services do not instantiate repositories internally from raw Session.
- [ ] Transaction ownership is explicit and consistent per workflow.
- [ ] One default response envelope policy documented and enforced.
- [ ] Endpoint auth/permission matrix documented and validated.
- [ ] UTC-aware timestamp writes only.
- [ ] Soft-delete policy documented per entity and consistently filtered.
- [ ] Search/filter/sort parameter naming standardized.
- [ ] Schema modules split by bounded context with explicit request/response types.
- [ ] Error handling follows standardized domain exception mapping.
- [ ] Logging/metrics/request-id policy applied uniformly.
