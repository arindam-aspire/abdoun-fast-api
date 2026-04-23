"""Application configuration (env-driven).

This module provides:
- `Settings`: a Pydantic model describing configuration values
- `get_settings()`: cached accessor for settings with validation and defaults

Defaults and validation messages are centralized in `app/utils/constants.py` to avoid
hardcoded text in this module.
"""

import os
import importlib.util
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel

# Load environment variables from .env file
# load_dotenv() automatically searches current directory and parent directories
load_dotenv()

from app.utils.constants import ConfigDefaults, ConfigErrorMessages, SystemMessages


def _get_database_url() -> str:
    """Return the database URL.

    Returns:
        Database URL from `DATABASE_URL` env var, otherwise a safe local default.
    """
    return os.getenv("DATABASE_URL", ConfigDefaults.DATABASE_URL)


def _parse_csv_env(name: str, default: str = "") -> list[str]:
    """Parse a comma-separated environment variable into a list of non-empty strings.

    Args:
        name: Environment variable name.
        default: Default value if the variable is not set.

    Returns:
        List of stripped, non-empty segments from the value (or default).
    """
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _get_env_str(
    primary: str,
    fallback_key: Optional[str] = None,
    *,
    default: Optional[str] = None,
) -> str:
    """Get a string from the environment with optional fallback key and default.

    Args:
        primary: Primary environment variable name.
        fallback_key: Optional alternate env key to try if primary is unset.
        default: Optional default value when both primary and fallback are unset.

    Returns:
        The value from primary, fallback_key, or default; empty string if none set.
    """
    value = os.getenv(primary)
    if value:
        return value
    if fallback_key:
        value = os.getenv(fallback_key)
        if value:
            return value
    return default if default is not None else ""


def _get_env_optional_str(primary: str, fallback_key: Optional[str] = None) -> Optional[str]:
    """Get an optional string from the environment with optional fallback key.

    Args:
        primary: Primary environment variable name.
        fallback_key: Optional alternate env key to try if primary is unset.

    Returns:
        The value from primary or fallback_key, or None if neither is set.
    """
    value = os.getenv(primary)
    if value:
        return value
    if fallback_key:
        return os.getenv(fallback_key)
    return None


class Settings(BaseModel):
    """Application settings loaded from environment variables.

    Notes:
        This model is instantiated by `get_settings()` and may be post-processed by
        `_apply_observability_defaults()` to disable features when dependencies are missing.
    """

    app_name: str = SystemMessages.APP_NAME
    environment: str = os.getenv("ENVIRONMENT", ConfigDefaults.ENVIRONMENT)
    debug: bool = os.getenv("DEBUG", ConfigDefaults.DEBUG).lower() == "true"

    database_url: str = _get_database_url()

    # SQLAlchemy connection pool tuning (env-driven).
    # These defaults are conservative and can be overridden per environment.
    db_pool_size: int = int(os.getenv("DB_POOL_SIZE", "5"))
    db_max_overflow: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    db_pool_timeout: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    db_pool_recycle: int = int(os.getenv("DB_POOL_RECYCLE", "1800"))
    db_pool_pre_ping: bool = os.getenv("DB_POOL_PRE_PING", "true").lower() == "true"

    api_v1_prefix: str = SystemMessages.API_V1_PREFIX

    # Safer default: explicit local frontend origin(s) rather than "*".
    cors_origins: list[str] = _parse_csv_env("CORS_ORIGINS", ConfigDefaults.CORS_ORIGINS)
    cors_allow_credentials: bool = os.getenv(
        "CORS_ALLOW_CREDENTIALS",
        ConfigDefaults.CORS_ALLOW_CREDENTIALS,
    ).lower() == "true"
    # When credentials=True, CORS spec forbids "*" for methods/headers; use explicit lists.
    cors_allow_methods: list[str] = _parse_csv_env(
        "CORS_ALLOW_METHODS",
        ConfigDefaults.CORS_ALLOW_METHODS,
    )
    cors_allow_headers: list[str] = _parse_csv_env(
        "CORS_ALLOW_HEADERS",
        ConfigDefaults.CORS_ALLOW_HEADERS,
    )
    cors_max_age: int = ConfigDefaults.CORS_MAX_AGE_SECONDS  # Preflight cache (seconds)
    
    # Azure OpenAI settings (optional, for geocoding fallback)
    azure_openai_key: Optional[str] = os.getenv("AZURE_OPENAI_KEY")
    azure_openai_endpoint: Optional[str] = os.getenv("AZURE_ENDPOINT")
    azure_openai_api_version: Optional[str] = os.getenv("AZURE_API_VERSION")
    azure_openai_deployment_name: Optional[str] = os.getenv("AZURE_DEPLOYMENT_NAME")

    # AWS Cognito Settings
    cognito_user_pool_id: str = _get_env_str("COGNITO_USER_POOL_ID")
    cognito_client_id: str = _get_env_str("COGNITO_APP_CLIENT_ID", "COGNITO_CLIENT_ID")
    cognito_client_secret: Optional[str] = _get_env_optional_str("COGNITO_APP_CLIENT_SECRET", "COGNITO_CLIENT_SECRET")
    cognito_region: str = _get_env_str("COGNITO_REGION", default="us-east-1")
    cognito_domain: str = _get_env_str("COGNITO_DOMAIN")
    social_redirect_uri: str = os.getenv(
        "SOCIAL_REDIRECT_URI",
        ConfigDefaults.SOCIAL_REDIRECT_URI,
    )
    
    # AWS Credentials (optional - boto3 will also check environment variables and ~/.aws/credentials)
    aws_access_key_id: Optional[str] = _get_env_optional_str("AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = _get_env_optional_str("AWS_SECRET_ACCESS_KEY")

    # Base URL for invite links (e.g. https://app.example.com)
    app_base_url: str = _get_env_str("APP_BASE_URL", default=ConfigDefaults.APP_BASE_URL)

    # -----------------------------------------------------------------------
    # Observability (opt-in / env-driven)
    # -----------------------------------------------------------------------
    metrics_enabled: bool = os.getenv("METRICS_ENABLED", "").lower() == "true"
    metrics_path: str = os.getenv("METRICS_PATH", ConfigDefaults.METRICS_PATH)

    otel_enabled: bool = os.getenv("OTEL_ENABLED", "").lower() == "true"
    otel_service_name: str = os.getenv("OTEL_SERVICE_NAME", "")

    sentry_dsn: str = os.getenv("SENTRY_DSN", "")
    sentry_enabled: bool = os.getenv("SENTRY_ENABLED", "").lower() == "true"

    slow_query_threshold_ms: int = int(
        os.getenv("SLOW_QUERY_THRESHOLD_MS", ConfigDefaults.SLOW_QUERY_THRESHOLD_MS)
    )
    dashboard_summary_scheduler_enabled: bool = os.getenv(
        "DASHBOARD_SUMMARY_SCHEDULER_ENABLED",
        "true",
    ).lower() == "true"
    dashboard_summary_schedule_time: str = os.getenv(
        "DASHBOARD_SUMMARY_SCHEDULE_TIME",
        "00:10",
    )


def _apply_observability_defaults(settings: Settings) -> None:
    """Apply safe observability defaults and dependency-based disables.

    Args:
        settings: Settings instance to mutate in-place.
    """
    # Sensible default: enable metrics in local/dev unless explicitly set.
    if "METRICS_ENABLED" not in os.environ:
        settings.metrics_enabled = settings.debug or settings.environment in {"local", "development"}

    # If a dependency isn't installed, the corresponding feature must be disabled.
    if settings.metrics_enabled and importlib.util.find_spec("prometheus_client") is None:
        settings.metrics_enabled = False

    if settings.otel_enabled and importlib.util.find_spec("opentelemetry.sdk") is None:
        settings.otel_enabled = False
    if not settings.otel_service_name:
        settings.otel_service_name = settings.app_name

    if settings.sentry_enabled and not settings.sentry_dsn:
        settings.sentry_enabled = False
    if settings.sentry_enabled and importlib.util.find_spec("sentry_sdk") is None:
        settings.sentry_enabled = False


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings.

    Loads env-driven Settings, validates CORS for production/staging, applies
    observability defaults (metrics/OTEL/Sentry), and caches the result.

    Returns:
        Validated Settings instance.

    Raises:
        ValueError: If CORS is misconfigured (e.g. "*" with credentials enabled).
    """
    settings = Settings()

    # Fail fast for insecure CORS in higher environments.
    if settings.environment in {"production", "staging"} and settings.cors_allow_credentials:
        if not settings.cors_origins or "*" in settings.cors_origins:
            raise ValueError(ConfigErrorMessages.INVALID_CORS_PROD_STAGING_WITH_CREDENTIALS)

    # Also protect local/dev from the unsafe "*" + credentials combination by default.
    if settings.cors_allow_credentials and ("*" in settings.cors_origins):
        raise ValueError(ConfigErrorMessages.INVALID_CORS_WITH_CREDENTIALS)

    _apply_observability_defaults(settings)

    return settings
