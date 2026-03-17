import os
import importlib.util
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel

# Load environment variables from .env file
# load_dotenv() automatically searches current directory and parent directories
load_dotenv()

from app.utils.constants import SystemMessages


def _get_database_url() -> str:
    """Get database URL from environment variable."""
    return os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/realestate")


def _parse_csv_env(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _get_env_str(
    primary: str,
    fallback_key: Optional[str] = None,
    *,
    default: Optional[str] = None,
) -> str:
    """Get required or optional string from env: try primary key, then fallback key, then default."""
    value = os.getenv(primary)
    if value:
        return value
    if fallback_key:
        value = os.getenv(fallback_key)
        if value:
            return value
    return default if default is not None else ""


def _get_env_optional_str(primary: str, fallback_key: Optional[str] = None) -> Optional[str]:
    """Get optional string from env: try primary key, then fallback key."""
    value = os.getenv(primary)
    if value:
        return value
    if fallback_key:
        return os.getenv(fallback_key)
    return None


class Settings(BaseModel):
    app_name: str = SystemMessages.APP_NAME
    environment: str = os.getenv("ENVIRONMENT", "local")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

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
    cors_origins: list[str] = _parse_csv_env("CORS_ORIGINS", "http://localhost:3000")
    cors_allow_credentials: bool = os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"
    # When credentials=True, CORS spec forbids "*" for methods/headers; use explicit lists.
    cors_allow_methods: list[str] = _parse_csv_env(
        "CORS_ALLOW_METHODS",
        "GET,POST,PUT,PATCH,DELETE,OPTIONS",
    )
    cors_allow_headers: list[str] = _parse_csv_env(
        "CORS_ALLOW_HEADERS",
        "Authorization,Content-Type,Accept,Origin,X-Requested-With",
    )
    cors_max_age: int = 600  # Preflight cache (seconds)
    
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
    social_redirect_uri: str = os.getenv("SOCIAL_REDIRECT_URI", "http://localhost:8000/api/v1/auth/callback")
    
    # AWS Credentials (optional - boto3 will also check environment variables and ~/.aws/credentials)
    aws_access_key_id: Optional[str] = _get_env_optional_str("AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = _get_env_optional_str("AWS_SECRET_ACCESS_KEY")

    # Base URL for invite links (e.g. https://app.example.com)
    app_base_url: str = _get_env_str("APP_BASE_URL", default="http://localhost:3000")

    # -----------------------------------------------------------------------
    # Observability (opt-in / env-driven)
    # -----------------------------------------------------------------------
    metrics_enabled: bool = os.getenv("METRICS_ENABLED", "").lower() == "true"
    metrics_path: str = os.getenv("METRICS_PATH", "/metrics")

    otel_enabled: bool = os.getenv("OTEL_ENABLED", "").lower() == "true"
    otel_service_name: str = os.getenv("OTEL_SERVICE_NAME", "")

    sentry_dsn: str = os.getenv("SENTRY_DSN", "")
    sentry_enabled: bool = os.getenv("SENTRY_ENABLED", "").lower() == "true"

    slow_query_threshold_ms: int = int(os.getenv("SLOW_QUERY_THRESHOLD_MS", "500"))


def _apply_observability_defaults(settings: Settings) -> None:
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
    settings = Settings()

    # Fail fast for insecure CORS in higher environments.
    if settings.environment in {"production", "staging"} and settings.cors_allow_credentials:
        if not settings.cors_origins or "*" in settings.cors_origins:
            raise ValueError(
                "Invalid CORS configuration: in production/staging with credentials enabled, "
                "CORS_ORIGINS must be a non-empty explicit list and cannot include '*'."
            )

    # Also protect local/dev from the unsafe "*" + credentials combination by default.
    if settings.cors_allow_credentials and ("*" in settings.cors_origins):
        raise ValueError(
            "Invalid CORS configuration: when CORS_ALLOW_CREDENTIALS=true, "
            "CORS_ORIGINS cannot include '*'."
        )

    _apply_observability_defaults(settings)

    return settings
