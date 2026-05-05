# Final Functionality Parity Report

Generated as part of the parallel refactor task pack closure.

## Legacy endpoint coverage

| Area | Legacy surface | Refactored package | Parity evidence |
|------|----------------|-------------------|-----------------|
| Auth / profile | `app/api/v1/routes/auth.py` | `app_refactored/domains/auth/` | `tests/refactor_parity/test_auth_parity.py` |
| Users / RBAC | `app/api/v1/routes/users.py` | `app_refactored/domains/users/` | `tests/refactor_parity/test_admin_users_parity.py` (with admin) |
| Admin dashboard + assignment | `admin.py`, `admin_properties.py` | `app_refactored/domains/admin/` | `tests/refactor_parity/test_admin_users_parity.py` |
| Agents | `agent.py`, `agents.py` | `app_refactored/domains/agents/` | `tests/refactor_parity/test_agents_parity.py` |
| Properties / search / import | `properties.py`, `search.py` | `app_refactored/domains/properties/` | `tests/refactor_parity/test_properties_parity.py` |
| Taxonomy | `locations.py`, `property_taxonomy.py` | `app_refactored/domains/taxonomy/` (custom router) | `tests/refactor_parity/test_taxonomy_parity.py` |
| Personalization | `favorites.py`, `saved_searches.py`, `recent_views.py` | `app_refactored/domains/personalization/` | `tests/refactor_parity/test_personalization_parity.py` |
| Uploads | `uploads.py` | `app_refactored/domains/uploads/` | `tests/refactor_parity/test_uploads_parity.py` |
| Owners | `owners.py` | `app_refactored/domains/owners/` | `tests/refactor_parity/test_owners_parity.py` |
| Submissions | `property_submissions.py`, `admin_property_submissions.py` | `app_refactored/domains/submissions/` | `tests/refactor_parity/test_submissions_parity.py` |
| Agent property list | `agent_properties.py` | Legacy only (not behind a refactored flag in this pack) | Shared router — same as pre-refactor wiring |
| Observability / schedulers / scripts | See `NON_API_FUNCTIONALITY_AUDIT.md` | Shared | Documented |

## Automated gates

- `pytest tests/refactor_parity/ -q` — **required green**
- `pytest tests/smoke/ -q` — **required green**
- `python scripts/check_contract_drift.py` — **no_contract_drift** (default flags)

## Blocking items

**None** at documentation time. Ongoing gaps must be recorded in `docs/refactor/MISSING_FUNCTIONALITY_REGISTER.md` before enabling the corresponding flag in production.

## Register reference

- `docs/refactor/MISSING_FUNCTIONALITY_REGISTER.md` — should contain **no unresolved critical** items before final cutover.
- `docs/refactor/SECURITY_DEBT_REGISTER.md` — known security debt (e.g. owners auth) documented for follow-up.
