"""Request-ID middleware: attaches a correlation id to each request and adds it to the response header."""

from __future__ import annotations

import importlib.util

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.utils.constants import RequestIdConstants
from app.utils.request_context import (
    new_request_id,
    sanitize_incoming_request_id,
    set_request_id,
)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a correlation id to each request and propagate it to responses."""

    header_name: str = RequestIdConstants.HEADER_NAME

    async def dispatch(self, request: Request, call_next) -> Response:
        """Read or generate request id, set context and OTEL attribute, then add id to response.

        Args:
            request: The incoming request (may contain X-Request-ID).
            call_next: Callable to invoke the next handler.

        Returns:
            The response with X-Request-ID header set.
        """
        incoming = sanitize_incoming_request_id(request.headers.get(self.header_name))
        request_id = incoming or new_request_id()

        set_request_id(request_id)
        try:
            if importlib.util.find_spec("opentelemetry") is not None:
                from opentelemetry.trace import get_current_span

                span = get_current_span()
                if span is not None:
                    span.set_attribute(RequestIdConstants.OTEL_ATTRIBUTE_REQUEST_ID, request_id)
        except Exception:  # pragma: no cover - OTEL must not break request handling
            pass
        try:
            response = await call_next(request)
        finally:
            # Avoid leaking request ids across tasks/threads.
            set_request_id(None)

        response.headers.setdefault(self.header_name, request_id)
        return response

