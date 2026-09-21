from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
import logging

from app.core.config import get_settings
from app.api.v1.router import api_router
from app.services.notifications.email.exceptions import EmailConfigurationError, EmailDeliveryError
from app.utils.api_response import error_payload
from app.utils.status_codes import (
    STATUS_CONFLICT,
    STATUS_INTERNAL_SERVER_ERROR,
    STATUS_OK,
    STATUS_SERVICE_UNAVAILABLE,
    STATUS_UNAUTHORIZED,
)


logger = logging.getLogger(__name__)


def _is_database_unreachable(exc: BaseException) -> bool:
    message = str(exc).casefold()
    return any(
        token in message
        for token in (
            "timed out",
            "timeout",
            "could not connect",
            "connection refused",
            "is the server running",
            "name or service not known",
            "could not translate host name",
        )
    )


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

    def _classified_http_error(status_code: int, message: str) -> str:
        lowered = message.casefold()
        if status_code == STATUS_UNAUTHORIZED or "auth" in lowered:
            return "AUTHENTICATION_ERROR"
        if "upload" in lowered or "media" in lowered or "file" in lowered:
            return "FILE_UPLOAD_ERROR"
        if status_code == STATUS_CONFLICT:
            return "CONFLICT"
        if status_code in {400, 422}:
            return "VALIDATION_ERROR"
        if status_code >= 500:
            return "INTERNAL_ERROR"
        return f"HTTP_{status_code}"

    @app.exception_handler(HTTPException)
    async def http_error_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict):
            error = dict(exc.detail)
            error.setdefault("code", _classified_http_error(exc.status_code, str(error.get("message") or "")))
            error.setdefault("message", "Request failed")
        else:
            message = str(exc.detail)
            error = error_payload(code=_classified_http_error(exc.status_code, message), message=message)
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

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(_request: Request, exc: IntegrityError) -> JSONResponse:
        logger.exception("Database integrity error")
        message = "A conflicting property record already exists"
        return JSONResponse(
            status_code=STATUS_CONFLICT,
            content={
                "success": False,
                "message": message,
                "data": None,
                "error": error_payload(
                    code="DATABASE_ERROR",
                    message=message,
                    details=[{"code": "duplicate_or_constraint", "message": message}],
                ),
                "meta": {},
            },
        )

    @app.exception_handler(OperationalError)
    async def database_operational_error_handler(_request: Request, exc: OperationalError) -> JSONResponse:
        logger.exception("Database operational error")
        if _is_database_unreachable(exc):
            message = "Database is unreachable"
            return JSONResponse(
                status_code=STATUS_SERVICE_UNAVAILABLE,
                content={
                    "success": False,
                    "message": message,
                    "data": None,
                    "error": error_payload(code="DATABASE_UNAVAILABLE", message=message),
                    "meta": {},
                },
            )
        message = "A database error prevented the request from completing"
        return JSONResponse(
            status_code=STATUS_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": message,
                "data": None,
                "error": error_payload(code="DATABASE_ERROR", message=message),
                "meta": {},
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(_request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("Database error")
        message = "A database error prevented the request from completing"
        return JSONResponse(
            status_code=STATUS_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": message,
                "data": None,
                "error": error_payload(code="DATABASE_ERROR", message=message),
                "meta": {},
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unexpected error")
        message = "An unexpected error prevented the request from completing"
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








