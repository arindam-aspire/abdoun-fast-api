"""Domain-level routers and services (feature-flagged from `app.api.v1.router`).

This package replaces the former top-level `app.domains` package: one `app` tree only.
ORM models remain in `app.models`; HTTP routes in `app.api.v1.routes` supply handlers
re-exported here until fully inlined.
"""
