from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings


RTL_LOCALES = {"ar"}


@lru_cache
def supported_locales() -> tuple[str, ...]:
    settings = get_settings()
    return tuple(locale.strip() for locale in settings.supported_locales.split(",") if locale.strip())


def normalize_locale(locale: str | None) -> str:
    settings = get_settings()
    fallback = settings.default_locale
    if not locale:
        return fallback

    candidate = locale.strip().lower()
    return candidate if candidate in supported_locales() else fallback


def is_rtl_locale(locale: str | None) -> bool:
    return normalize_locale(locale) in RTL_LOCALES
