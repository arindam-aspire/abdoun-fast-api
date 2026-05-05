"""Property submissions domain (legacy router re-exports)."""

from __future__ import annotations

from app.api.v1.routes.admin_property_submissions import router as admin_property_submissions_router
from app.api.v1.routes.property_submissions import router as property_submissions_router

__all__ = ["admin_property_submissions_router", "property_submissions_router"]
