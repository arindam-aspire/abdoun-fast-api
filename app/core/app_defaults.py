from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core.json_config import load_json_config


@lru_cache
def get_currency_symbols() -> dict[str, str]:
    data = load_json_config("currencies.json")
    return {
        str(code).upper(): str(symbol)
        for code, symbol in (data.get("symbols") or {}).items()
    }


@lru_cache
def get_supported_currencies() -> frozenset[str]:
    data = load_json_config("currencies.json")
    configured = data.get("supported") or ["JOD", "USD", "GBP", "INR"]
    return frozenset(str(code).upper() for code in configured)


@lru_cache
def get_geocoding_config() -> dict[str, Any]:
    return load_json_config("geocoding.json")


@lru_cache
def get_property_taxonomy() -> list[dict[str, Any]]:
    data = load_json_config("property_taxonomy.json")
    return list(data or [])
