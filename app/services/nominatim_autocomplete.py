"""OpenStreetMap Nominatim autocomplete (free geocoding suggestions)."""

from __future__ import annotations

import time
from functools import lru_cache
from typing import Any, Optional

import requests

from app.utils.constants import GeocodingConstants


class NominatimAutocompleteService:
    """Fetch place suggestions from Nominatim with simple in-process caching."""

    def __init__(self) -> None:
        self._last_request_at = 0.0

    def _rate_limit(self) -> None:
        delay = GeocodingConstants.RATE_LIMIT_DELAY
        elapsed = time.time() - self._last_request_at
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_at = time.time()

    @lru_cache(maxsize=512)
    def _cached_search(self, query: str, limit: int) -> tuple[dict[str, Any], ...]:
        self._rate_limit()
        params = {
            "q": query,
            "format": "json",
            "limit": limit,
            "addressdetails": 0,
        }
        headers = {"User-Agent": GeocodingConstants.USER_AGENT}
        response = requests.get(
            GeocodingConstants.NOMINATIM_BASE_URL,
            params=params,
            headers=headers,
            timeout=(GeocodingConstants.TIMEOUT_CONNECT, GeocodingConstants.TIMEOUT_READ),
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            return tuple()
        return tuple(item for item in data if isinstance(item, dict))

    def search(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        text = (query or "").strip()
        if len(text) < 2:
            return []
        try:
            return list(self._cached_search(text.lower(), limit))
        except Exception:
            return []


nominatim_autocomplete_service = NominatimAutocompleteService()
