"""Admin domain package."""

from app.domains.admin.router import (
    admin_dashboard_router,
    admin_properties_router,
)

__all__ = ["admin_dashboard_router", "admin_properties_router"]
