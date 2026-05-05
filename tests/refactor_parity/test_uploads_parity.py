"""Parity: uploads router."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.v1.routes import uploads as legacy_uploads
from app.utils.constants import ApiRoutes, SystemMessages
from app.domains.uploads import uploads_router
from tests.refactor_parity.route_parity_utils import assert_route_parity


def test_uploads_route_signatures_match() -> None:
    base = f"{SystemMessages.API_V1_PREFIX}{ApiRoutes.UPLOADS_PREFIX}"
    legacy = FastAPI()
    legacy.include_router(legacy_uploads.router, prefix=base, tags=[ApiRoutes.UPLOADS_TAG])
    ref = FastAPI()
    ref.include_router(uploads_router, prefix=base, tags=[ApiRoutes.UPLOADS_TAG])
    assert_route_parity(legacy, ref)
