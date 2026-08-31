from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation

import requests
from fastapi import HTTPException

from app.core.app_defaults import get_supported_currencies
from app.core.config import get_settings
from app.utils.status_codes import STATUS_BAD_REQUEST, STATUS_SERVICE_UNAVAILABLE

JOD_QUANTIZE = Decimal("0.001")
_CACHE_TTL_SECONDS = 300
_rate_cache: dict[str, tuple[float, dict[str, Decimal]]] = {}


class ExchangeRateError(Exception):
    """Raised when live exchange rates cannot be resolved."""


def _parse_rates(raw_rates: dict[str, object]) -> dict[str, Decimal]:
    parsed: dict[str, Decimal] = {}
    for code, value in raw_rates.items():
        try:
            parsed[str(code).upper()] = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            continue
    return parsed


def _fetch_open_er_api(base_currency: str) -> dict[str, Decimal]:
    settings = get_settings()
    url = f"{settings.exchange_rate_api_base_url.rstrip('/')}/{base_currency.upper()}"
    response = requests.get(url, timeout=settings.exchange_rate_timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    if payload.get("result") != "success":
        raise ExchangeRateError("Exchange rate provider returned an unsuccessful result")
    rates = _parse_rates(payload.get("rates") or {})
    if not rates:
        raise ExchangeRateError("Exchange rate provider returned no rates")
    return rates


def _fetch_fawazahmed0_api(base_currency: str) -> dict[str, Decimal]:
    settings = get_settings()
    base = base_currency.lower()
    url = f"{settings.exchange_rate_fallback_api_base_url.rstrip('/')}/{base}.json"
    response = requests.get(url, timeout=settings.exchange_rate_timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    raw_rates = payload.get(base)
    if not isinstance(raw_rates, dict):
        raise ExchangeRateError("Fallback exchange rate provider returned invalid data")
    rates = _parse_rates(raw_rates)
    if not rates:
        raise ExchangeRateError("Fallback exchange rate provider returned no rates")
    return rates


def _get_rates_for_base(base_currency: str) -> dict[str, Decimal]:
    base = base_currency.upper()
    cached = _rate_cache.get(base)
    now = time.monotonic()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    last_error: Exception | None = None
    for fetcher in (_fetch_open_er_api, _fetch_fawazahmed0_api):
        try:
            rates = fetcher(base)
            _rate_cache[base] = (now, rates)
            return rates
        except (ExchangeRateError, requests.RequestException) as exc:
            last_error = exc
            continue

    raise ExchangeRateError(str(last_error) if last_error else "Unable to fetch exchange rates")


def get_jod_exchange_rate(from_currency: str) -> Decimal:
    """Return how many JOD equal one unit of ``from_currency``."""
    source = (from_currency or get_settings().default_currency).upper()
    if source == "JOD":
        return Decimal("1")
    rates = _get_rates_for_base(source)
    jod_rate = rates.get("JOD")
    if jod_rate is None or jod_rate <= 0:
        raise ExchangeRateError(f"No JOD exchange rate available for {source}")
    return jod_rate


def convert_amount_to_jod(amount: Decimal, from_currency: str) -> Decimal:
    converted = amount * get_jod_exchange_rate(from_currency)
    return converted.quantize(JOD_QUANTIZE)


def convert_amount_to_jod_or_http_error(amount: Decimal, from_currency: str, *, field_name: str) -> Decimal:
    try:
        return convert_amount_to_jod(amount, from_currency)
    except ExchangeRateError as exc:
        raise HTTPException(
            status_code=STATUS_SERVICE_UNAVAILABLE,
            detail=f"Unable to convert {field_name} from {from_currency} to JOD: {exc}",
        ) from exc


def assert_supported_currency(currency: str | None, *, field_name: str = "currency") -> str:
    settings = get_settings()
    normalized = (currency or settings.default_currency).strip().upper() or settings.default_currency
    supported = get_supported_currencies()
    if normalized not in supported:
        raise HTTPException(
            status_code=STATUS_BAD_REQUEST,
            detail=f"{field_name} must be one of: {', '.join(sorted(supported))}",
        )
    return normalized
