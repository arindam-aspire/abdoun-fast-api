"""Add security-related HTTP response headers (CSP, HSTS, X-Frame-Options, etc.)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings
from app.utils.constants import DEV_ENVIRONMENTS, SecurityHeadersConstants


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Set security headers on every response; HSTS only when not in local/development."""

    async def dispatch(self, request: Request, call_next) -> Response:
        """Call next handler then set default security headers on the response.

        Args:
            request: The incoming request.
            call_next: Callable to invoke the next handler.

        Returns:
            The response with security headers set.
        """
        response = await call_next(request)

        response.headers.setdefault(
            SecurityHeadersConstants.X_CONTENT_TYPE_OPTIONS,
            SecurityHeadersConstants.NOSNIFF,
        )
        response.headers.setdefault(
            SecurityHeadersConstants.X_FRAME_OPTIONS,
            SecurityHeadersConstants.DENY,
        )
        response.headers.setdefault(
            SecurityHeadersConstants.X_XSS_PROTECTION,
            SecurityHeadersConstants.XSS_BLOCK,
        )
        response.headers.setdefault(
            SecurityHeadersConstants.REFERRER_POLICY,
            SecurityHeadersConstants.REFERRER_STRICT_ORIGIN,
        )
        response.headers.setdefault(
            SecurityHeadersConstants.PERMISSIONS_POLICY,
            SecurityHeadersConstants.PERMISSIONS_RESTRICTIVE,
        )
        response.headers.setdefault(
            SecurityHeadersConstants.CONTENT_SECURITY_POLICY,
            SecurityHeadersConstants.CSP_API_BASELINE,
        )

        settings = get_settings()
        if not settings.debug and settings.environment not in DEV_ENVIRONMENTS:
            response.headers.setdefault(
                SecurityHeadersConstants.STRICT_TRANSPORT_SECURITY,
                SecurityHeadersConstants.HSTS_MAX_AGE,
            )

        return response

