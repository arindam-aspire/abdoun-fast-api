"""Auth / profile domain (legacy router re-export)."""

from __future__ import annotations

from app.api.v1.routes.auth import router as auth_router

__all__ = ["auth_router"]
