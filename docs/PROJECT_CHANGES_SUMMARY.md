# Project changes summary

This document summarizes the refactor and related work applied to this repository (parallel “refactor pack,” single-package consolidation, cleanup, and follow-up commits).

---

## 1. Architecture

- **One FastAPI app:** `app.main:app` remains the only production entrypoint.
- **Domain layer:** Former `app_refactored` was **removed**; domain routers and taxonomy code live under **`app.domains`** (`app/domains/`).
- **Startup-only routing:** `app/api/v1/router.py` chooses legacy vs `app.domains` imports using **environment flags** (see `app/core/config.py`). No per-request router swapping.
- **Models:** SQLAlchemy ORM models stay in **`app/models/`**; domain code imports them from there.

---

## 2. Feature flags (`app/core/config.py`)

Boolean settings (default **`false`**, overridable via env), for example:

- `use_refactored_taxonomy`, `use_refactored_properties`, `use_refactored_personalization`, `use_refactored_uploads`, `use_refactored_owners`, `use_refactored_agents`, `use_refactored_submissions`, `use_refactored_admin`, `use_refactored_users`, `use_refactored_auth`

Corresponding env names use `USE_REFACTORED_*` (e.g. `USE_REFACTORED_TAXONOMY=true`).

---

## 3. `app.domains` layout

| Area | Role |
|------|------|
| `app/domains/taxonomy/` | Custom router + service + repository (parity with legacy taxonomy endpoints). |
| `app/domains/properties/`, `search` re-exports | Same `APIRouter` instances as `app.api.v1.routes` (behavior preserved). |
| Other `app/domains/*` | Re-export routers for auth, agents, admin, users, owners, personalization, uploads, submissions. |
| `app/domains/core/`, `shared/` | Small shared primitives (e.g. result/errors, pagination helpers). |

---

## 4. Tests

- **`tests/refactor_parity/`** — Parity harness (`conftest`, `parity_client`, `assertions`, `route_parity_utils`) and per-domain route / response checks.
- **`tests/smoke/`** — Lightweight smoke tests (e.g. health, OpenAPI has v1 paths).

---

## 5. Scripts and baselines (archived)

Refactor-only tooling and generated baselines were moved under **`to_be_deleted/`** (see `to_be_deleted/README.md`), including:

- `instructions/` (task pack)
- `docs_refactor/` (OpenAPI/DB baselines, checklists, runbooks)
- `scripts_refactor/` (`check_contract_drift.py`, `generate_refactor_baseline.py`, `build_db_md.py`)
- Various audit / inventory markdown files

Restore paths from there if you need baselines or drift checks in CI again.

---

## 6. Migration checkpoints

- **`docs/MIGRATION_CHECKPOINTS.md`** — Steps for consolidating `app_refactored` → `app.domains` and verification commands.

---

## 7. OpenAPI docs & security headers (later commit)

- **`Settings.openapi_docs_enabled`** — Controlled by `OPENAPI_DOCS_ENABLED`; defaults on in local/dev-style environments (see `DEV_ENVIRONMENTS`).
- **`app/main.py`** — `docs_url` / `redoc_url` use `api_v1_prefix` when docs are enabled.
- **`app/middleware/security.py`** + **`app/utils/constants.py`** — Relaxed **CSP** for `/api/v1/docs` and `/api/v1/redoc` so Swagger UI can load CDN assets (`CSP_OPENAPI_DOCS`).

---

## 8. Git reference (this branch)

Typical commits on `review_and_refractor` include:

- Consolidation of domain code under `app.domains` and removal of `app_refactored`.
- Large commit bundling `to_be_deleted` archive, parity/smoke tests, and related files (per your history).
- **`feat: OpenAPI docs toggle and relaxed CSP for Swagger/ReDoc`** — the four-file change above.

Use `git log --oneline` for exact hashes and ordering.

---

## 9. What did not change (by design)

- Default flags remain **off** unless env is set: production behavior matches pre-refactor routing until you enable flags and restart.
- No intentional HTTP contract changes when all flags are `false` (parity tests and prior drift tooling targeted that).
- Historical Alembic revisions were not rewritten.

---

*For archived refactor checklists and security/owners notes, see files under `to_be_deleted/docs_refactor/`.*
