"""Uploads domain (legacy router re-export)."""

from __future__ import annotations

from app.api.v1.routes.uploads import router as uploads_router

__all__ = ["uploads_router"]
