"""Personalization domain package."""

from app.domains.personalization.router import (
    favorites_router,
    recent_views_router,
    saved_searches_router,
)

__all__ = ["favorites_router", "recent_views_router", "saved_searches_router"]
