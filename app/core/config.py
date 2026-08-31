import os
from functools import lru_cache
from urllib.parse import quote_plus

from dotenv import load_dotenv
from pydantic import BaseModel

# Load environment variables from .env file
# load_dotenv() automatically searches current directory and parent directories
load_dotenv()

LOCAL_CORS_ALLOWED_ORIGIN_REGEX = (
    r"^https?://("
    r"localhost|127\.0\.0\.1|0\.0\.0\.0|"
    r"10(?:\.\d{1,3}){3}|"
    r"192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}"
    r")(?::\d+)?$"
)


def _env_str(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    cleaned = value.strip().strip("\"'")
    return cleaned if cleaned else default


def _env_int(name: str, default: int) -> int:
    value = _env_str(name)
    if value is None:
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = _env_str(name)
    if value is None:
        return default
    return float(value)


def _env_bool(name: str, default: bool) -> bool:
    value = _env_str(name)
    if value is None:
        return default
    return value.lower() == "true"


def _csv_values(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    return [item.strip().strip("\"'") for item in raw_value.split(",") if item.strip().strip("\"'")]


def _get_cors_allowed_origins() -> str:
    values: list[str] = []
    for env_name in ("CORS_ALLOWED_ORIGINS", "CORS_ORIGINS"):
        values.extend(_csv_values(os.getenv(env_name)))
    if not values:
        values = _csv_values(_env_str("CORS_DEFAULT_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"))
    return ",".join(dict.fromkeys(values))


def _get_cors_allowed_origin_regex() -> str | None:
    configured = os.getenv("CORS_ALLOWED_ORIGIN_REGEX")
    if configured is not None:
        return configured.strip().strip("\"'") or None

    environment = (_env_str("ENVIRONMENT", "local") or "local").lower()
    if environment in {"local", "dev", "development", "test"}:
        return LOCAL_CORS_ALLOWED_ORIGIN_REGEX
    return None


def _get_database_url() -> str:
    """Get database URL from environment variable."""
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT")
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    if all([db_host, db_port, db_name, db_user, db_password]):
        encoded_user = quote_plus(db_user or "")
        encoded_password = quote_plus(db_password or "")
        return f"postgresql+psycopg2://{encoded_user}:{encoded_password}@{db_host}:{db_port}/{db_name}"

    return _env_str(
        "DATABASE_URL_FALLBACK",
        "postgresql+psycopg2://postgres:postgres@localhost:5432/realestate",
    ) or "postgresql+psycopg2://postgres:postgres@localhost:5432/realestate"


class Settings(BaseModel):
    app_name: str = _env_str("APP_NAME", "Abdoun Real Estate API") or "Abdoun Real Estate API"
    environment: str = _env_str("ENVIRONMENT", "local") or "local"
    debug: bool = _env_bool("DEBUG", False)

    database_url: str = _get_database_url()
    db_sslmode: str = _env_str("DB_SSLMODE", "require") or "require"

    api_v1_prefix: str = _env_str("API_V1_PREFIX", "/api/v1") or "/api/v1"
    cors_allowed_origins: str = _get_cors_allowed_origins()
    cors_allowed_origin_regex: str | None = _get_cors_allowed_origin_regex()

    notification_email_mode: str = _env_str("NOTIFICATION_EMAIL_MODE", "log") or "log"
    notification_sms_mode: str = _env_str("NOTIFICATION_SMS_MODE", "log") or "log"
    notification_poll_interval_seconds: int = _env_int("NOTIFICATION_POLL_INTERVAL_SECONDS", 30)
    ses_from_email: str | None = _env_str("SES_FROM_EMAIL")
    ses_from_name: str | None = _env_str("SES_FROM_NAME")
    email_otp_verification_subject: str = (
        _env_str("EMAIL_OTP_VERIFICATION_SUBJECT", "Verify your email address")
        or "Verify your email address"
    )
    expose_otp_in_response: bool = _env_bool(
        "EXPOSE_OTP_IN_RESPONSE",
        (_env_str("ENVIRONMENT", "local") or "local").lower() in {"local", "development", "dev"},
    )
    supported_locales: str = _env_str("SUPPORTED_LOCALES", "en,ar,fr,es") or "en,ar,fr,es"
    default_locale: str = _env_str("DEFAULT_LOCALE", "en") or "en"
    rtl_locales: str = _env_str("RTL_LOCALES", "ar") or "ar"
    auth_token_secret: str = (
        _env_str("AUTH_TOKEN_SECRET")
        or _env_str("SECRET_KEY")
        or "abdoun-dev-token-secret"
    )
    auth_access_token_seconds: int = _env_int("AUTH_ACCESS_TOKEN_SECONDS", 3600)
    auth_refresh_token_seconds: int = _env_int("AUTH_REFRESH_TOKEN_SECONDS", 604800)
    auth_otp_ttl_seconds: int = _env_int("AUTH_OTP_TTL_SECONDS", 600)
    agency_invitation_ttl_seconds: int = _env_int("AGENCY_INVITATION_TTL_SECONDS", 900)
    agency_password_setup_ttl_seconds: int = _env_int("AGENCY_PASSWORD_SETUP_TTL_SECONDS", 900)
    agent_invitation_ttl_seconds: int = _env_int("AGENT_INVITATION_TTL_SECONDS", 900)
    frontend_base_url: str = (
        _env_str("FRONTEND_BASE_URL")
        or _env_str("APP_BASE_URL")
        or "http://localhost:3000"
    ).rstrip("/")
    allow_owner_multiple_agencies: bool = _env_bool("ALLOW_OWNER_MULTIPLE_AGENCIES", False)

    aws_s3_bucket: str | None = _env_str("AWS_S3_BUCKET", "")
    aws_region: str = _env_str("AWS_REGION", "us-west-2") or "us-west-2"
    aws_access_key_id: str | None = _env_str("AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str | None = _env_str("AWS_SECRET_ACCESS_KEY")

    cognito_region: str = (
        _env_str("COGNITO_REGION")
        or _env_str("AWS_REGION")
        or "us-west-2"
    )
    cognito_user_pool_id: str = _env_str("COGNITO_USER_POOL_ID", "") or ""
    cognito_app_client_id: str = _env_str("COGNITO_APP_CLIENT_ID", "") or ""
    cognito_app_client_secret: str = _env_str("COGNITO_APP_CLIENT_SECRET", "") or ""
    cognito_domain: str = _env_str("COGNITO_DOMAIN", "") or ""
    social_redirect_uri: str | None = _env_str("SOCIAL_REDIRECT_URI")
    facebook_app_id: str | None = _env_str("FACEBOOK_APP_ID")
    facebook_app_secret: str | None = _env_str("FACEBOOK_APP_SECRET")
    media_url_presign_enabled: bool = _env_bool("MEDIA_URL_PRESIGN_ENABLED", True)
    media_url_presign_expires_seconds: int = _env_int("MEDIA_URL_PRESIGN_EXPIRES_SECONDS", 3600)
    media_upload_presign_expires_seconds: int = _env_int("MEDIA_UPLOAD_PRESIGN_EXPIRES_SECONDS", 900)

    # Azure OpenAI settings (optional, for geocoding fallback)
    azure_openai_key: str | None = _env_str("AZURE_OPENAI_KEY")
    azure_openai_endpoint: str | None = _env_str("AZURE_ENDPOINT")
    azure_openai_api_version: str | None = _env_str("AZURE_API_VERSION")
    azure_openai_deployment_name: str | None = _env_str("AZURE_DEPLOYMENT_NAME")
    azure_openai_temperature: float = _env_float("AZURE_OPENAI_TEMPERATURE", 0.3)
    azure_openai_max_tokens: int = _env_int("AZURE_OPENAI_MAX_TOKENS", 100)

    default_currency: str = (_env_str("DEFAULT_CURRENCY", "JOD") or "JOD").upper()
    exchange_rate_api_base_url: str = (
        _env_str("EXCHANGE_RATE_API_BASE_URL", "https://open.er-api.com/v6/latest")
        or "https://open.er-api.com/v6/latest"
    )
    exchange_rate_fallback_api_base_url: str = (
        _env_str(
            "EXCHANGE_RATE_FALLBACK_API_BASE_URL",
            "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies",
        )
        or "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies"
    )
    exchange_rate_timeout_seconds: int = _env_int("EXCHANGE_RATE_TIMEOUT_SECONDS", 10)
    default_measurement_unit: str = _env_str("DEFAULT_MEASUREMENT_UNIT", "sqm") or "sqm"
    default_country: str = _env_str("DEFAULT_COUNTRY", "Jordan") or "Jordan"
    default_country_id: int = _env_int("DEFAULT_COUNTRY_ID", 1)
    default_city: str = _env_str("DEFAULT_CITY", "Amman") or "Amman"
    untitled_property_title: str = _env_str("UNTITLED_PROPERTY_TITLE", "Untitled property") or "Untitled property"
    exclusive_badge_label: str = _env_str("EXCLUSIVE_BADGE_LABEL", "Exclusive") or "Exclusive"
    search_default_limit: int = _env_int("SEARCH_DEFAULT_LIMIT", 50)
    search_default_offset: int = _env_int("SEARCH_DEFAULT_OFFSET", 0)
    search_max_limit: int = _env_int("SEARCH_MAX_LIMIT", 200)
    property_search_default_radius_km: float = _env_float("PROPERTY_SEARCH_DEFAULT_RADIUS_KM", 10)

    geocoding_nominatim_base_url: str = (
        _env_str("GEOCODING_NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org/search")
        or "https://nominatim.openstreetmap.org/search"
    )
    geocoding_user_agent: str = (
        _env_str("GEOCODING_USER_AGENT")
        or f"{_env_str('APP_NAME', 'Abdoun Real Estate API')}/1.0"
    )
    geocoding_rate_limit_delay: float = _env_float("GEOCODING_RATE_LIMIT_DELAY", 1.1)
    geocoding_timeout_connect: int = _env_int("GEOCODING_TIMEOUT_CONNECT", 10)
    geocoding_timeout_read: int = _env_int("GEOCODING_TIMEOUT_READ", 30)
    geocoding_extra_delay_after_403: int = _env_int("GEOCODING_EXTRA_DELAY_AFTER_403", 2)
    geocoding_example_latitude: float = _env_float("GEOCODING_EXAMPLE_LATITUDE", 31.9539)
    geocoding_example_longitude: float = _env_float("GEOCODING_EXAMPLE_LONGITUDE", 35.9106)

    whatsapp_base_url: str = (_env_str("WHATSAPP_BASE_URL", "https://wa.me") or "https://wa.me").rstrip("/")
    google_maps_embed_base_url: str = (
        _env_str("GOOGLE_MAPS_EMBED_BASE_URL", "https://maps.google.com/maps")
        or "https://maps.google.com/maps"
    ).rstrip("/")
    google_maps_embed_zoom: int = _env_int("GOOGLE_MAPS_EMBED_ZOOM", 15)


@lru_cache
def get_settings() -> Settings:
    return Settings()
