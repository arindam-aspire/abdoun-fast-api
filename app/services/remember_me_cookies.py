"""HttpOnly Secure cookies for Remember Me opaque refresh tokens."""
from __future__ import annotations

from typing import Literal

from fastapi import Response

from app.core.config import Settings
from app.utils.constants import RememberMeConstants


def _samesite_value(settings: Settings) -> Literal["lax", "strict", "none"]:
    raw = (settings.remember_me_cookie_samesite or "lax").lower()
    if raw in ("strict", "none", "lax"):
        return raw  # type: ignore[return-value]
    return "lax"


def set_remember_me_cookie(
    *,
    response: Response,
    settings: Settings,
    opaque_token: str,
    max_age_seconds: int,
) -> None:
    """Attach Remember Me cookie (opaque token only; Cognito RT stays server-side encrypted)."""
    capped = min(max_age_seconds, RememberMeConstants.MAX_SESSION_SECONDS)
    secure = not settings.debug
    samesite = _samesite_value(settings)
    if samesite == "none" and not secure:
        secure = True
    kwargs: dict = {
        "key": RememberMeConstants.COOKIE_NAME,
        "value": opaque_token,
        "max_age": capped,
        "httponly": True,
        "secure": secure,
        "samesite": samesite,
        "path": RememberMeConstants.COOKIE_PATH,
    }
    domain = settings.remember_me_cookie_domain
    if domain:
        kwargs["domain"] = domain
    response.set_cookie(**kwargs)


def clear_remember_me_cookie(*, response: Response, settings: Settings) -> None:
    """Remove Remember Me cookie (logout / invalidation)."""
    secure = not settings.debug
    samesite = _samesite_value(settings)
    kwargs: dict = {
        "key": RememberMeConstants.COOKIE_NAME,
        "path": RememberMeConstants.COOKIE_PATH,
        "secure": secure,
        "samesite": samesite,
        "httponly": True,
    }
    domain = settings.remember_me_cookie_domain
    if domain:
        kwargs["domain"] = domain
    response.delete_cookie(**kwargs)
