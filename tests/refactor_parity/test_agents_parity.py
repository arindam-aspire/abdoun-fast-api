"""Parity: agent + agents routers."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.v1.routes import agent as legacy_agent
from app.api.v1.routes import agents as legacy_agents
from app.utils.constants import ApiRoutes, SystemMessages
from app.domains.agents import agent_router, agents_router
from tests.refactor_parity.route_parity_utils import assert_route_parity


def test_agents_route_signatures_match() -> None:
    v1 = SystemMessages.API_V1_PREFIX
    legacy = FastAPI()
    legacy.include_router(
        legacy_agent.router,
        prefix=f"{v1}{ApiRoutes.AGENT_PREFIX}",
        tags=[ApiRoutes.AGENT_TAG],
    )
    legacy.include_router(
        legacy_agents.router,
        prefix=f"{v1}{ApiRoutes.AGENTS_PREFIX}",
        tags=[ApiRoutes.AGENTS_TAG],
    )
    ref = FastAPI()
    ref.include_router(
        agent_router,
        prefix=f"{v1}{ApiRoutes.AGENT_PREFIX}",
        tags=[ApiRoutes.AGENT_TAG],
    )
    ref.include_router(
        agents_router,
        prefix=f"{v1}{ApiRoutes.AGENTS_PREFIX}",
        tags=[ApiRoutes.AGENTS_TAG],
    )
    assert_route_parity(legacy, ref)
