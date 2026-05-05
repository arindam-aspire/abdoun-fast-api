# API architecture review — SOLID and layering

**Scope:** FastAPI v1 surface (`app/api/v1/`), dependencies (`app/api/v1/deps/`), and how routes delegate to services and repositories.  
**Audience:** Senior full-stack / backend architects.  
**Related:** This complements security and operations findings in `FINAL_FASTAPI_BACKEND_AUDIT.md` and `FASTAPI_BACKEND_AUDIT_VALIDATION.md`; it focuses on **design principles** and **maintainability**, not a full security audit.

---

## 1. Executive summary

The codebase shows a **mature default pattern**: routers are thin, construct or validate HTTP inputs, and call **services** wired through **FastAPI `Depends`**. Many domains use **repositories** behind those services. That aligns well with **Dependency Inversion** (high-level API depends on abstractions you inject) and, in the best modules, **Single Responsibility** at the route level.

Gaps are mostly **consistency** and **boundary clarity**: a few routers mix transport concerns (pagination math, compatibility shims, side effects), some responses bypass shared envelope types, **`/owners` has no authentication**, and a few modules bundle multiple actor roles (admin vs agent vs public) in one file. Addressing these moves the API toward a more **balanced** SOLID posture without requiring a rewrite.

---

## 2. Layering as implemented

| Layer | Role | Typical location |
|--------|------|------------------|
| **HTTP / transport** | Routing, query/path/body binding, auth dependencies, status codes | `app/api/v1/routes/*.py` |
| **Composition root (per request)** | `Depends` factories: DB session, repositories, services | `app/api/v1/deps/*.py` |
| **Application / domain orchestration** | Workflows, validation, transactions, calls to infra | `app/services/*.py` |
| **Persistence** | SQLAlchemy-centric data access | `app/repositories/*.py` |

**Observation:** Route modules generally **do not** import `Session` or execute raw ORM queries. That is a strong sign the earlier “logic in routers” anti-pattern has been largely retired for v1 (grep over `app/api/v1/routes` shows no direct `Session` / `sqlalchemy` usage).

---

## 3. SOLID principles — applied to this API

### 3.1 Single Responsibility Principle (SRP)

**What “good” looks like here:** One route function = map HTTP → one service call (or a small, explicit orchestration), plus auth.

**Strengths**

- **Crisp examples:** `property_submissions.py`, `favorites.py`, `saved_searches.py`, `uploads.py`, `admin_properties.py` — mostly delegate immediately to a dedicated service.
- **Auth** is largely expressed as dependencies (`get_current_user`, `require_role`, `require_permission`), which keeps authorization out of business logic.

**Friction**

- **`agents.py`** combines admin lifecycle, public/compat invite validation, onboarding compatibility, assignments, and **agent** dashboard summary under one router. Each *function* is still small, but the **module** has multiple reasons to change (SRP at file/team ownership level).
- **`admin.py`** duplicates pagination assembly (`math.ceil`, `PaginationInfo`) that also appears in **`agent.py`** and **`agents.py`** (property performance). The responsibility “build paginated admin dashboard DTO” is repeated at the HTTP edge instead of living in one place (service or shared presenter).
- **`properties.get_property`** couples “fetch detail” with “track recent view” and a broad `try/except` for logging. Tracking is a **cross-cutting concern**; keeping it in the route works but blurs “one job per handler” unless documented as intentional.

**Recommendations**

- Split `agents.py` by actor or subdomain (e.g. `agents_admin.py`, `agents_public_onboarding.py`, `agents_self_service.py`) or by feature folders if the team prefers vertical slices.
- Move repeated pagination wrapping for dashboard performance into **`AdminDashboardService`** (or a tiny `DashboardResponseBuilder`) so routes only pass through the result.
- Consider a domain event or background task for recent-view tracking to keep `get_property` purely read-oriented (optional; trade-off vs complexity).

---

### 3.2 Open/Closed Principle (OCP)

**Idea:** Extend behavior (new filters, new auth rules, new fields) without editing many stable call sites.

**Strengths**

- **New endpoints** are usually added as new functions + service methods, with **limited ripple** if services stay cohesive.
- **Dependency injection** makes it feasible to swap implementations in tests (`Depends` providers).

**Friction**

- **Compatibility layers** in `agents.py` (`submit_onboarding_compat`, query vs body token, phone normalization) encode evolving clients **inside** the router. That is pragmatic but means new client quirks often require **editing** this code path (OCP stress).
- **Query-param aliases** (`limit` vs `pageSize`, `sort_by` vs `sortBy`) are spread across list endpoints; extending pagination conventions may require touching multiple handlers.

**Recommendations**

- Centralize “compat” adapters in a small module or Pydantic validators so the router only calls `service.submit_onboarding(...)`.
- Define a **single pagination helper** or shared `PaginatedRequest` pattern to reduce per-route alias logic.

---

### 3.3 Liskov Substitution Principle (LSP)

LSP matters most where you have **interfaces, inheritance, or polymorphic services**. This codebase is mostly **concrete classes** injected via `Depends`, which is normal for FastAPI.

**Observation:** Services are not widely programmed behind `Protocol` / ABC types in the route layer. That does not violate LSP; it means **substitutability is convention + DI**, not enforced by types.

**Recommendation (optional):** For ports that you mock heavily (e.g. `AuthService`, storage), introduce **`Protocol`** definitions in a `ports` or `interfaces` package so tests and alternate implementations stay substitutable without subclassing a concrete service.

---

### 3.4 Interface Segregation Principle (ISP)

**Idea:** Callers should not depend on fat interfaces they do not use.

**Strengths**

- Route handlers typically depend on **one service** (e.g. `FavoriteService`, `PropertySubmissionService`), not a god-object facade.

**Friction**

- **`AgentService`** (inferred from `agents.py`) is likely a **wide** surface: invites, CRUD, assignments, onboarding, etc. From the **router’s** perspective each method is segregated, but the **service class** may still be a large dependency for maintainers.
- **`PropertySubmissionService`** serves **both** agent submission flows and **admin** moderation (`admin_property_submissions.py`). That can be correct (one aggregate) or a signal to split **read models vs write workflows** if the class grows further.

**Recommendations**

- If `AgentService` or `PropertySubmissionService` exceeds a comfortable size, split by **use case** (`AgentInviteService`, `AgentLifecycleService`, …) while keeping routes stable.
- Keep admin vs agent **route modules** separate (already done for submissions); mirror that in services if boundaries blur.

---

### 3.5 Dependency Inversion Principle (DIP)

**Idea:** High-level modules depend on abstractions; infrastructure implements them.

**Strengths**

- **`Depends(get_*_service)`** consistently inverts construction: routes declare *what* they need, not *how* to build it.
- **Repositories** injected into services (`OwnerService(repo)`, `AgentPropertyService` with two repos) match classic DIP for persistence.

**Friction**

- Some **`Depends` providers** construct services with concrete repositories inline (e.g. `AgentPropertyService` in `deps/agent_properties.py`). That is still DIP at the **route** level; the “abstraction” is the service type, not necessarily an interface.
- **Return types** like `dict` on `locations.py` and `property_taxonomy.py` couple callers (OpenAPI consumers) to **unstructured** payloads; the server does not invert a stable contract type at the HTTP boundary.

**Recommendations**

- Replace `-> dict` with **Pydantic response models** for taxonomy endpoints to lock the contract and improve ISP for API clients.
- Where valuable, define **`Protocol`** for `GeoSearchService` / import services to ease testing without subclassing.

---

## 4. Security and boundaries (SOLID-adjacent)

SOLID is not security, but **clear boundaries** support least privilege.

| Area | Finding |
|------|---------|
| **`/owners` router** | Endpoints use `OwnerService` but **no `Depends(get_current_user)` or role checks** appear on the router. If these routes are exposed publicly, this violates least privilege and makes **ownership of the “owner” aggregate** unclear at the API boundary. |
| **Auth router** | Delegates to `AuthService`; sensitive routes use rate limits (`slowapi`) on several flows — good separation of policy from handler body. |
| **Admin vs permission-based** | Mix of `require_role(ADMIN)` and `require_permission(...)` is consistent with RBAC but implies **two mental models** for authorization; document when to use which. |

**Recommendation:** Treat unauthenticated owner CRUD as **technical debt** unless explicitly internal-only (e.g. behind network policy). Prefer explicit `require_permission` or service-to-service auth.

---

## 5. Response model consistency

The API mixes patterns:

- **`StandardResponse[T]`** — dominant for user-facing JSON envelopes.
- **Raw models** — e.g. `PropertyListResponse` / `PropertyDetail` on some property routes, `ImportResponse` on CSV import.
- **`dict`** — location and property taxonomy.

For **clients and evolution**, leaning on **typed response models everywhere** improves contract clarity (DIP at the HTTP boundary) and reduces accidental breaking changes.

---

## 6. Sync vs async

Many handlers are **synchronous** `def` while performing I/O-bound service work. FastAPI runs these in a threadpool. This is not a SOLID violation but affects **scalability and consistency**. A future pass could align on `async def` where the stack supports it, or document the intentional sync model.

---

## 7. Prioritized improvement backlog (architecture)

1. **High — boundary:** Add authentication and authorization to **`/owners`** (or document and enforce network-level isolation).
2. **High — consistency:** Typed responses for **`/location-taxonomy`** and **`/property-taxonomy`**.
3. **Medium — SRP:** Reduce duplication of **dashboard pagination** assembly; optionally extract **recent-view** side effect from `get_property`.
4. **Medium — SRP/OCP:** Thin **`agents.py`** by moving compat onboarding and validation sanitizers behind a dedicated adapter/service.
5. **Lower — DIP:** Introduce **`Protocol`** for heavily mocked or swappable services; split oversized service classes by use case when file size/complexity hurts reviews.

---

## 8. Conclusion

The v1 API layer is **already aligned** with SOLID in its **dominant pattern**: thin routes, injected services, and repositories for many flows. The remaining work is **balancing** principles through **consistency** (envelopes and schemas), **clear security boundaries** (notably owners), and **module/service granularity** (large routers and repeated HTTP-side DTO assembly). None of this requires abandoning the current stack; it is incremental hardening suitable for a growing team and codebase.
