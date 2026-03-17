"""Unit tests for app.core.config."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys

import pytest

from app.core.config import (
    Settings,
    _apply_observability_defaults,
    _get_database_url,
    _get_env_optional_str,
    _get_env_str,
    _parse_csv_env,
    get_settings,
)


def test_get_database_url_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert "postgresql" in _get_database_url() and "5432" in _get_database_url()


def test_get_database_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host/db")
    assert _get_database_url() == "postgresql://u:p@host/db"


def test_parse_csv_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("X", "a , b , c ")
    assert _parse_csv_env("X") == ["a", "b", "c"]
    assert _parse_csv_env("MISSING", "d,e") == ["d", "e"]


def test_get_env_str_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("P", "v1")
    assert _get_env_str("P") == "v1"


def test_get_env_str_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("P", raising=False)
    monkeypatch.setenv("F", "v2")
    assert _get_env_str("P", "F") == "v2"


def test_get_env_str_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("P", raising=False)
    monkeypatch.delenv("F", raising=False)
    assert _get_env_str("P", "F", default="d") == "d"
    assert _get_env_str("P", default=None) == ""


def test_get_env_optional_str_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("P", "v1")
    assert _get_env_optional_str("P") == "v1"


def test_get_env_optional_str_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("P", raising=False)
    monkeypatch.setenv("F", "v2")
    assert _get_env_optional_str("P", "F") == "v2"


def test_get_env_optional_str_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("P", raising=False)
    monkeypatch.delenv("F", raising=False)
    assert _get_env_optional_str("P", "F") is None


def test_apply_observability_defaults_metrics_enabled_when_not_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("METRICS_ENABLED", raising=False)
    settings = Settings(environment="local", debug=False)
    _apply_observability_defaults(settings)
    assert settings.metrics_enabled is True


def test_apply_observability_defaults_metrics_disabled_when_prometheus_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("METRICS_ENABLED", raising=False)
    _real_find = importlib.util.find_spec

    def _find(name: str):
        if name == "prometheus_client":
            return None
        return _real_find(name)

    monkeypatch.setattr(importlib.util, "find_spec", _find)
    settings = Settings(environment="local", metrics_enabled=True)
    _apply_observability_defaults(settings)
    assert settings.metrics_enabled is False


def test_apply_observability_defaults_otel_disabled_when_sdk_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _real_find = importlib.util.find_spec

    def _find(name: str):
        if name == "opentelemetry.sdk":
            return None
        return _real_find(name)

    monkeypatch.setattr(importlib.util, "find_spec", _find)
    settings = Settings(otel_enabled=True)
    _apply_observability_defaults(settings)
    assert settings.otel_enabled is False


def test_apply_observability_defaults_otel_service_name_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(otel_enabled=True, otel_service_name="")
    orig_find = importlib.util.find_spec

    def _find(name: str):
        if name == "opentelemetry.sdk":
            return type("Spec", (), {"origin": None})()
        return orig_find(name)

    monkeypatch.setattr(importlib.util, "find_spec", _find)
    _apply_observability_defaults(settings)
    assert settings.otel_service_name == settings.app_name


def test_apply_observability_defaults_sentry_disabled_when_no_dsn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(sentry_enabled=True, sentry_dsn="")
    _apply_observability_defaults(settings)
    assert settings.sentry_enabled is False


def test_apply_observability_defaults_sentry_disabled_when_sdk_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _real_find_spec = importlib.util.find_spec

    def _find(name: str):
        if name == "sentry_sdk":
            return None
        return _real_find_spec(name)

    monkeypatch.setattr(importlib.util, "find_spec", _find)
    settings = Settings(sentry_enabled=True, sentry_dsn="https://key@o.ingest.sentry.io/1")
    _apply_observability_defaults(settings)
    assert settings.sentry_enabled is False


def test_get_settings_cors_production_staging_rejects_star() -> None:
    """CORS validation: production/staging + credentials + * raises (env read at import)."""
    result = subprocess.run(
        [sys.executable, "-c", "from app.core.config import get_settings; get_settings()"],
        env={**os.environ, "ENVIRONMENT": "production", "CORS_ALLOW_CREDENTIALS": "true", "CORS_ORIGINS": "*"},
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    )
    assert result.returncode != 0
    assert "CORS" in (result.stderr + result.stdout)


def test_get_settings_cors_credentials_rejects_star() -> None:
    """CORS validation: credentials + * raises (env read at import)."""
    result = subprocess.run(
        [sys.executable, "-c", "from app.core.config import get_settings; get_settings()"],
        env={**os.environ, "CORS_ALLOW_CREDENTIALS": "true", "CORS_ORIGINS": "*"},
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    )
    assert result.returncode != 0
    assert "cannot include" in (result.stderr + result.stdout)
