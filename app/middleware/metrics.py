from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.observability.metrics import HTTP_REQUEST_DURATION_SECONDS, HTTP_REQUESTS_TOTAL


def _get_route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return request.url.path


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """Collect basic HTTP request metrics suitable for Prometheus scraping."""

    def __init__(self, app, *, excluded_paths: set[str] | None = None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._excluded_paths = excluded_paths or set()

    async def dispatch(self, request: Request, call_next) -> Response:
        path = _get_route_template(request)
        if path in self._excluded_paths:
            return await call_next(request)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed = time.perf_counter() - start

        HTTP_REQUEST_DURATION_SECONDS.labels(method=request.method, path=path).observe(elapsed)
        HTTP_REQUESTS_TOTAL.labels(method=request.method, path=path, status=str(response.status_code)).inc()
        return response

