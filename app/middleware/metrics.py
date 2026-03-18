"""Prometheus HTTP metrics middleware; records request duration and count by method, path, and status."""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.observability.metrics import HTTP_REQUEST_DURATION_SECONDS, HTTP_REQUESTS_TOTAL


def _get_route_template(request: Request) -> str:
    """Resolve the route template (path pattern) for metrics labels, or fall back to request path.

    Args:
        request: The Starlette request; scope["route"].path or url.path used.

    Returns:
        Route template string (e.g. "/api/v1/users/{id}") or raw path.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return request.url.path


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """Collect basic HTTP request metrics suitable for Prometheus scraping."""

    def __init__(self, app, *, excluded_paths: set[str] | None = None) -> None:  # type: ignore[no-untyped-def]
        """Register the ASGI app and optional paths to exclude from metrics.

        Args:
            app: The ASGI application to wrap.
            excluded_paths: Paths (e.g. /metrics) to skip when recording metrics.
        """
        super().__init__(app)
        self._excluded_paths = excluded_paths or set()

    async def dispatch(self, request: Request, call_next) -> Response:
        """Run the next handler and record duration/count metrics for non-excluded paths.

        Args:
            request: The incoming request.
            call_next: Callable to invoke the next handler.

        Returns:
            The response from the downstream handler.
        """
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

