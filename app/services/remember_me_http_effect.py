"""HTTP-level side effects for Remember Me (Set-Cookie / Delete-Cookie)."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Response

from app.core.config import Settings
from app.services.remember_me_cookies import clear_remember_me_cookie, set_remember_me_cookie


@dataclass(frozen=True)
class RememberMeHttpEffect:
    """Returned from AuthService for routes to apply to the outgoing Response."""

    set_cookie_opaque: str | None = None
    cookie_max_age_seconds: int = 0
    clear_cookie: bool = False


def apply_remember_me_http_effect(
    *, response: Response, settings: Settings, effect: RememberMeHttpEffect
) -> None:
    if effect.clear_cookie:
        clear_remember_me_cookie(response=response, settings=settings)
    if effect.set_cookie_opaque:
        set_remember_me_cookie(
            response=response,
            settings=settings,
            opaque_token=effect.set_cookie_opaque,
            max_age_seconds=effect.cookie_max_age_seconds,
        )
