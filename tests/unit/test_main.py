"""Unit tests for app.main create_app."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.main import create_app


def test_create_app_basic() -> None:
    """create_app returns a FastAPI app with health and API router."""
    app = create_app()
    assert app.title
    assert app.version == "1.0.0"


@patch("app.main.get_settings")
def test_create_app_with_sentry_enabled(mock_get_settings: MagicMock) -> None:
    settings = MagicMock()
    settings.sentry_enabled = True
    settings.sentry_dsn = "https://key@o.ingest.sentry.io/1"
    settings.environment = "test"
    settings.debug = False
    settings.otel_enabled = False
    settings.metrics_enabled = False
    settings.app_name = "Test"
    settings.api_v1_prefix = "/api/v1"
    settings.cors_origins = ["http://localhost:3000"]
    settings.cors_allow_credentials = False
    settings.cors_allow_methods = ["GET", "POST"]
    settings.cors_allow_headers = ["Authorization"]
    settings.metrics_path = "/metrics"
    mock_get_settings.return_value = settings
    with patch("app.observability.sentry.init_sentry") as mock_sentry:
        app = create_app()
        mock_sentry.assert_called_once_with(dsn=settings.sentry_dsn, environment=settings.environment)


@patch("app.main.get_settings")
def test_create_app_with_otel_enabled(mock_get_settings: MagicMock) -> None:
    settings = MagicMock()
    settings.sentry_enabled = False
    settings.debug = False
    settings.otel_enabled = True
    settings.otel_service_name = "test-svc"
    settings.metrics_enabled = False
    settings.app_name = "Test"
    settings.api_v1_prefix = "/api/v1"
    settings.cors_origins = ["http://localhost:3000"]
    settings.cors_allow_credentials = False
    settings.cors_allow_methods = ["GET"]
    settings.cors_allow_headers = ["Authorization"]
    settings.metrics_path = "/metrics"
    mock_get_settings.return_value = settings
    with patch("app.observability.tracing.init_tracing"), patch(
        "opentelemetry.instrumentation.requests.RequestsInstrumentor"
    ), patch("opentelemetry.instrumentation.fastapi.FastAPIInstrumentor") as mock_instr:
        app = create_app()
        mock_instr.instrument_app.assert_called_once_with(app)


@patch("app.main.get_settings")
def test_create_app_with_metrics_enabled(mock_get_settings: MagicMock) -> None:
    settings = MagicMock()
    settings.sentry_enabled = False
    settings.debug = False
    settings.otel_enabled = False
    settings.metrics_enabled = True
    settings.metrics_path = "/metrics"
    settings.app_name = "Test"
    settings.api_v1_prefix = "/api/v1"
    settings.cors_origins = ["http://localhost:3000"]
    settings.cors_allow_credentials = False
    settings.cors_allow_methods = ["GET"]
    settings.cors_allow_headers = ["Authorization"]
    mock_get_settings.return_value = settings
    app = create_app()
    # Metrics route is registered
    routes = [r.path for r in app.routes if hasattr(r, "path")]
    assert "/metrics" in routes


@patch("app.main.get_settings")
def test_create_app_metrics_endpoint_returns_prometheus_output(mock_get_settings: MagicMock) -> None:
    """Hit the metrics endpoint to cover main.py lines 75-76."""
    settings = MagicMock()
    settings.sentry_enabled = False
    settings.debug = False
    settings.otel_enabled = False
    settings.metrics_enabled = True
    settings.metrics_path = "/metrics"
    settings.app_name = "Test"
    settings.api_v1_prefix = "/api/v1"
    settings.cors_origins = ["http://localhost:3000"]
    settings.cors_allow_credentials = False
    settings.cors_allow_methods = ["GET"]
    settings.cors_allow_headers = ["Authorization"]
    mock_get_settings.return_value = settings
    app = create_app()
    from fastapi.testclient import TestClient
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "content-type" in r.headers and "text" in r.headers.get("content-type", "").lower()
