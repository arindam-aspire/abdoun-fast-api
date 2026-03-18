"""Initialize OpenTelemetry tracing from env (OTLP or console in debug); must not break startup."""
from __future__ import annotations

import os


def init_tracing(*, service_name: str) -> None:
    """Initialize OpenTelemetry tracing; OTLP if OTEL_EXPORTER_OTLP_ENDPOINT set, else console in debug.

    Args:
        service_name: Service name for the trace resource.
    """
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
    else:
        # Helpful for local debugging without extra infra.
        if os.getenv("DEBUG", "false").lower() == "true":
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)

