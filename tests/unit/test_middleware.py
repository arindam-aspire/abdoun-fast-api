"""Unit tests for middleware (metrics, request_id, security)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.middleware.metrics import PrometheusMetricsMiddleware, _get_route_template
from app.middleware.request_id import RequestIdMiddleware
from app.middleware.security import SecurityHeadersMiddleware
from app.utils.constants import RequestIdConstants, SecurityHeadersConstants
from app.utils.status_codes import HTTPStatus


def test_get_route_template_uses_route_path() -> None:
    request = MagicMock()
    request.scope = {"route": MagicMock(path="/api/v1/items")}
    request.url.path = "/api/v1/items"
    assert _get_route_template(request) == "/api/v1/items"


def test_get_route_template_fallback_to_url_path() -> None:
    request = MagicMock()
    request.scope = {"route": MagicMock(path=None)}
    request.url.path = "/health"
    assert _get_route_template(request) == "/health"


def test_get_route_template_empty_path_fallback() -> None:
    request = MagicMock()
    request.scope = {"route": MagicMock(path="")}
    request.url.path = "/fallback"
    assert _get_route_template(request) == "/fallback"


def test_prometheus_metrics_middleware_excluded_path() -> None:
    async def _run() -> None:
        middleware = PrometheusMetricsMiddleware(AsyncMock(), excluded_paths={"/metrics"})
        request = MagicMock()
        request.method = "GET"
        request.scope = {"route": MagicMock(path="/metrics")}
        request.url.path = "/metrics"
        call_next = AsyncMock(return_value=MagicMock(status_code=HTTPStatus.OK))
        resp = await middleware.dispatch(request, call_next)
        assert resp.status_code == HTTPStatus.OK

    asyncio.run(_run())


def test_request_id_middleware_sets_header() -> None:
    async def _run() -> None:
        app = AsyncMock()
        middleware = RequestIdMiddleware(app)
        request = MagicMock()
        request.headers = {}
        response = MagicMock()
        response.headers = {}
        call_next = AsyncMock(return_value=response)
        resp = await middleware.dispatch(request, call_next)
        assert "X-Request-ID" in resp.headers

    asyncio.run(_run())


def test_request_id_middleware_sets_span_attribute_when_otel_present() -> None:
    async def _run() -> None:
        mock_span = MagicMock()
        with patch("importlib.util.find_spec", return_value=MagicMock()):
            with patch("opentelemetry.trace.get_current_span", return_value=mock_span):
                app = AsyncMock()
                middleware = RequestIdMiddleware(app)
                request = MagicMock()
                request.headers = {}
                response = MagicMock()
                response.headers = {}
                call_next = AsyncMock(return_value=response)
                await middleware.dispatch(request, call_next)
                mock_span.set_attribute.assert_called_once()
                assert mock_span.set_attribute.call_args[0][0] == RequestIdConstants.OTEL_ATTRIBUTE_REQUEST_ID

    asyncio.run(_run())


def test_security_headers_middleware_adds_headers() -> None:
    async def _run() -> None:
        app = AsyncMock()
        middleware = SecurityHeadersMiddleware(app)
        request = MagicMock()
        response = MagicMock()
        response.headers = {}
        call_next = AsyncMock(return_value=response)
        resp = await middleware.dispatch(request, call_next)
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"

    asyncio.run(_run())


def test_security_headers_middleware_adds_hsts_when_not_debug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import get_settings
    from app.middleware import security as security_mod

    monkeypatch.setattr(
        security_mod,
        "get_settings",
        lambda: MagicMock(debug=False, environment="production"),
    )

    async def _run() -> None:
        app = AsyncMock()
        middleware = SecurityHeadersMiddleware(app)
        request = MagicMock()
        response = MagicMock()
        response.headers = {}
        call_next = AsyncMock(return_value=response)
        resp = await middleware.dispatch(request, call_next)
        assert resp.headers.get(SecurityHeadersConstants.STRICT_TRANSPORT_SECURITY) is not None

    asyncio.run(_run())
