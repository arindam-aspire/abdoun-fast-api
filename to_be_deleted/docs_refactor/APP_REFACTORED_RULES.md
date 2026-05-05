# app_refactored Rules

- One production FastAPI app only: `app.main:app`.
- SQLAlchemy models stay in `app/models/` and are imported from there.
- No copied ORM definitions are allowed under `app_refactored/`.
- No DB migrations are part of `app_refactored` migration tasks.
- Refactored routers are included only through startup-time feature flags.
- Feature flags default to legacy behavior (`False`) until parity is proven.

