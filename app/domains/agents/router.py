"""Agents domain: self-service + admin agent APIs (legacy router re-exports)."""

from __future__ import annotations

from app.api.v1.routes.agent import router as agent_router
from app.api.v1.routes.agents import router as agents_router

__all__ = ["agent_router", "agents_router"]
