"""Submissions domain package."""

from app.domains.submissions.router import (
    admin_property_submissions_router,
    property_submissions_router,
)

__all__ = ["admin_property_submissions_router", "property_submissions_router"]
