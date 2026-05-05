# Security Debt Register

| Area | Finding | Risk | Mitigation / owner |
|------|---------|------|---------------------|
| Owners API | `app/api/v1/routes/owners.py` endpoints do not declare `Depends(get_current_user)` or permission checks at the router layer. Behavior is preserved intentionally during refactor; `app_refactored` re-exports the same router. | Unauthenticated access to owner CRUD if deployed without upstream protection. | Add auth/RBAC in a dedicated hardening task; gate with API gateway or private network until then. |
