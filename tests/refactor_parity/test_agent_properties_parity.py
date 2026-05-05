"""Parity: agent-properties router (legacy-only mount; ensures stable wiring reference)."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.v1.routes import agent_properties as legacy_ap
from app.utils.constants import ApiRoutes, SystemMessages
from tests.refactor_parity.route_parity_utils import assert_route_parity


def test_agent_properties_route_signatures_stable() -> None:
    """Same router mounted twice should yield identical route maps (sanity baseline)."""
    base = f"{SystemMessages.API_V1_PREFIX}{ApiRoutes.AGENT_PROPERTIES_PREFIX}"
    a = FastAPI()
    a.include_router(legacy_ap.router, prefix=base, tags=[ApiRoutes.AGENT_PROPERTIES_TAG])
    b = FastAPI()
    b.include_router(legacy_ap.router, prefix=base, tags=[ApiRoutes.AGENT_PROPERTIES_TAG])
    assert_route_parity(a, b)
