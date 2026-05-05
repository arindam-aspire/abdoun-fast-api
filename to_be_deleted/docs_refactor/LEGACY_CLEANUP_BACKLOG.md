# Legacy Cleanup Backlog

**Do not delete** legacy modules until refactored paths have been stable in production for at least one release cycle and rollback is no longer required.

## Candidates for future removal or thinning

| Location | Notes |
|----------|--------|
| `app/api/v1/routes/*.py` | Today these remain the **source of truth** for handlers; refactored packages re-export the same routers. Removal would require moving handler code into `app_refactored/` intentionally. |
| Duplicate service wiring | If domains gain native `app_refactored` services, legacy `app/services/*` may be deduplicated gradually. |
| Feature flags | After sustained stability, flags could be collapsed or removed in a major version (coordination with ops). |

## Non-goals (immediate)

- Deleting `app/models/` ORM definitions (explicitly out of scope for this refactor).
- Editing historical Alembic revisions.
