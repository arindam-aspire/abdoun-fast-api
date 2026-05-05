"""Admin dashboard and admin property assignment (legacy router re-exports)."""

from __future__ import annotations

from app.api.v1.routes.admin import router as admin_dashboard_router
from app.api.v1.routes.admin_properties import router as admin_properties_router

__all__ = ["admin_dashboard_router", "admin_properties_router"]
