# Abdoun Parallel Refactor Task Pack v3

This pack contains 19 files: session rules + 18 ordered tasks.

## Corrected Architecture

- One production FastAPI app only: `app.main:app`.
- `app_refactored/` is a clean internal implementation package.
- Route switching happens only at startup using settings flags.
- SQLAlchemy ORM models remain in `app/models/`.
- No copied ORM models in `app_refactored/`.
- Parity tests compare legacy and refactored behavior before any switch.
- Auth parity uses fake user dependency overrides.
- Write endpoint parity uses rollback where possible, otherwise response-shape-only plus explicit gap flag.

## Task Order

0. Cursor session rules
1. Baseline and functionality inventory
2. app_refactored scaffold
3. Parity test harness
4. Startup feature flag routing policy
5. Taxonomy
6. Properties/search/geo/import
7. Personalization
8. Uploads/media
9. Owners
10. Agents
11. Submissions
12. Admin/users/RBAC/dashboard
13. Auth/profile
14. Observability/schedulers/scripts
15. Domain switchover/canary
16. Frontend impact report
17. Missing functionality audit
18. Final cutover and legacy cleanup plan

## Non-negotiable Rule

Do not switch a domain until its parity test passes and the missing functionality register has no unresolved blocker for that domain.
