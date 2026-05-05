"""Owners domain (legacy router re-export)."""

from __future__ import annotations

from app.api.v1.routes.owners import router as owners_router

__all__ = ["owners_router"]
