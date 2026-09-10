from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.api.v1.router import api_router
from app.services.notifications.email.exceptions import EmailConfigurationError, EmailDeliveryError
from app.utils.api_response import error_payload
from app.utils.status_codes import STATUS_INTERNAL_SERVER_ERROR, STATUS_OK, STATUS_SERVICE_UNAVAILABLE


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
    )
    allowed_origins = [
        origin.strip()
        for origin in settings.cors_allowed_origins.split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_origin_regex=settings.cors_allowed_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        details = []
        for error in exc.errors():
            location = [str(part) for part in error.get("loc", ()) if part not in {"body", "query", "path"}]
            details.append(
                {
                    "field": ".".join(location) or None,
                    "code": error.get("type") or "invalid_value",
                    "message": error.get("msg") or "Invalid value",
                }
            )
        message = details[0]["message"] if details else "Request validation failed"
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "message": message,
                "data": None,
                "error": error_payload(code="VALIDATION_ERROR", message=message, details=details),
                "meta": {},
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict):
            error = dict(exc.detail)
            error.setdefault("code", f"HTTP_{exc.status_code}")
            error.setdefault("message", "Request failed")
        else:
            error = error_payload(code=f"HTTP_{exc.status_code}", message=str(exc.detail))
        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content={
                "success": False,
                "message": error["message"],
                "data": None,
                "error": error,
                "meta": {},
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
        message = "An unexpected error prevented the property request from completing"
        return JSONResponse(
            status_code=STATUS_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": message,
                "data": None,
                "error": error_payload(code="INTERNAL_ERROR", message=message),
                "meta": {},
            },
        )

    @app.exception_handler(EmailConfigurationError)
    async def email_configuration_error_handler(_request: Request, exc: EmailConfigurationError) -> JSONResponse:
        return JSONResponse(
            status_code=STATUS_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": str(exc),
                "data": None,
                "error": error_payload(
                    code="email_configuration_error",
                    message=str(exc),
                ),
                "meta": {},
            },
        )

    @app.exception_handler(EmailDeliveryError)
    async def email_delivery_error_handler(_request: Request, _exc: EmailDeliveryError) -> JSONResponse:
        return JSONResponse(
            status_code=STATUS_SERVICE_UNAVAILABLE,
            content={
                "success": False,
                "message": "Unable to send email notification",
                "data": None,
                "error": error_payload(
                    code="email_delivery_error",
                    message="Unable to send email notification",
                ),
                "meta": {},
            },
        )
    
    # Health check endpoint for Docker
    @app.get("/health")
    async def health_check():
        """Health check endpoint for Docker health checks."""
        return JSONResponse(
            content={"status": "healthy", "service": "realestate-api"},
            status_code=STATUS_OK
        )
    
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()








