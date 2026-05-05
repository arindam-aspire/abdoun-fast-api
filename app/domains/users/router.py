"""Users / RBAC domain (legacy router re-export)."""

from __future__ import annotations

from app.api.v1.routes.users import router as users_router

__all__ = ["users_router"]
