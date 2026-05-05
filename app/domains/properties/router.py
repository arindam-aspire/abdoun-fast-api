"""Properties domain routers (refactored package entrypoint).

Re-exports the same legacy `APIRouter` instances so `use_refactored_properties`
can mount them with correct OpenAPI tags without duplicating handlers.

FastAPI does not support `include_router(..., tags=...)` on a nested router whose
child declares a `""` path; mounting these two routers separately at the v1 layer
matches the legacy wiring exactly.
"""

from __future__ import annotations

from app.api.v1.routes.properties import router as properties_router
from app.api.v1.routes.search import router as search_router

__all__ = ["properties_router", "search_router"]
