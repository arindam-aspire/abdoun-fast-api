"""Unit tests for observability (sentry, tracing)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.utils.request_context import set_request_id


def test_init_sentry_calls_sdk_init_and_before_send_adds_request_id() -> None:
    with patch("sentry_sdk.init") as mock_init:
        from app.observability.sentry import init_sentry

        init_sentry(dsn="https://key@o.ingest.sentry.io/1", environment="test")
        mock_init.assert_called_once()
        kwargs = mock_init.call_args[1]
        assert "before_send" in kwargs
        before_send = kwargs["before_send"]
        set_request_id("req-123")
        try:
            event = {}
            result = before_send(event, {})
            assert result is not None
            assert result.get("tags", {}).get("request_id") == "req-123"
        finally:
            set_request_id(None)

        event2 = {}
        set_request_id(None)
        result2 = before_send(event2, {})
        assert result2 is not None


def test_init_tracing_sets_provider() -> None:
    with patch("opentelemetry.trace.set_tracer_provider") as mock_set:
        with patch("opentelemetry.sdk.trace.TracerProvider") as mock_provider_cls:
            with patch("opentelemetry.sdk.resources.Resource") as mock_resource:
                mock_provider = MagicMock()
                mock_provider_cls.return_value = mock_provider
                mock_resource.create.return_value = MagicMock()

                from app.observability.tracing import init_tracing

                init_tracing(service_name="test-svc")
                mock_set.assert_called_once_with(mock_provider)


def test_init_tracing_with_otlp_endpoint() -> None:
    with patch.dict("os.environ", {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318"}):
        with patch("opentelemetry.trace.set_tracer_provider"):
            with patch("opentelemetry.sdk.trace.TracerProvider") as mock_provider_cls:
                with patch("opentelemetry.sdk.trace.export.BatchSpanProcessor"):
                    with patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"):
                        mock_provider = MagicMock()
                        with patch("opentelemetry.sdk.trace.TracerProvider", return_value=mock_provider):
                            with patch("opentelemetry.sdk.resources.Resource"):
                                from app.observability.tracing import init_tracing

                                init_tracing(service_name="svc")
                                mock_provider.add_span_processor.assert_called()


def test_init_tracing_debug_console_exporter() -> None:
    with patch.dict("os.environ", {"OTEL_EXPORTER_OTLP_ENDPOINT": "", "DEBUG": "true"}):
        with patch("opentelemetry.trace.set_tracer_provider"):
            with patch("opentelemetry.sdk.trace.TracerProvider") as mock_provider_cls:
                with patch("opentelemetry.sdk.trace.export.BatchSpanProcessor"):
                    with patch("opentelemetry.sdk.trace.export.ConsoleSpanExporter"):
                        mock_provider = MagicMock()
                        mock_provider_cls.return_value = mock_provider
                        with patch("opentelemetry.sdk.resources.Resource"):
                            from app.observability.tracing import init_tracing

                            init_tracing(service_name="svc")
                            mock_provider.add_span_processor.assert_called()
