"""Personalization domain: favorites, saved searches, recent views (legacy router re-exports)."""

from __future__ import annotations

from app.api.v1.routes.favorites import router as favorites_router
from app.api.v1.routes.recent_views import router as recent_views_router
from app.api.v1.routes.saved_searches import router as saved_searches_router

__all__ = ["favorites_router", "recent_views_router", "saved_searches_router"]
