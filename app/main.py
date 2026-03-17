from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import get_settings
from app.core.limiter import limiter
from app.middleware.request_id import RequestIdMiddleware
from app.middleware.security import SecurityHeadersMiddleware
from app.api.v1.router import api_router
from app.utils.constants import SystemMessages
from app.utils.status_codes import STATUS_OK


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.sentry_enabled:
        from app.observability.sentry import init_sentry

        init_sentry(dsn=settings.sentry_dsn, environment=settings.environment)

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        debug=settings.debug,
        docs_url="/api/v1/docs" if settings.debug else None,
        redoc_url="/api/v1/redoc" if settings.debug else None,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    if settings.otel_enabled:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor

        from app.observability.tracing import init_tracing

        init_tracing(service_name=settings.otel_service_name)
        RequestsInstrumentor().instrument()
        FastAPIInstrumentor.instrument_app(app)

    # Correlation IDs should be set as early as possible.
    app.add_middleware(RequestIdMiddleware)
    if settings.metrics_enabled:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
        from app.middleware.metrics import PrometheusMetricsMiddleware

        # Avoid collecting metrics about the scrape itself.
        app.add_middleware(PrometheusMetricsMiddleware, excluded_paths={settings.metrics_path})
    app.add_middleware(SecurityHeadersMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
        max_age=settings.cors_max_age,
    )
    
    # Health check endpoint for Docker
    @app.get("/health")
    async def health_check():
        """Health check endpoint for Docker health checks."""
        return JSONResponse(
            content={"status": SystemMessages.HEALTHY, "service": SystemMessages.SERVICE_NAME},
            status_code=STATUS_OK
        )

    if settings.metrics_enabled:
        @app.get(settings.metrics_path, include_in_schema=False)
        async def metrics():
            from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
            return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
