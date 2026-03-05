from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.api.v1.router import api_router
from app.utils.constants import SystemMessages
from app.utils.status_codes import STATUS_OK


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        debug=settings.debug,
        docs_url="/api/v1/docs" if settings.debug else None,
        redoc_url="/api/v1/redoc" if settings.debug else None,
    )

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

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
