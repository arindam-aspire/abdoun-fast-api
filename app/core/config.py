import os
from functools import lru_cache
from urllib.parse import quote_plus

from dotenv import load_dotenv
from pydantic import BaseModel

# Load environment variables from .env file
# load_dotenv() automatically searches current directory and parent directories
load_dotenv()

from app.utils.constants import SystemMessages

LOCAL_CORS_ALLOWED_ORIGIN_REGEX = (
    r"^https?://("
    r"localhost|127\.0\.0\.1|0\.0\.0\.0|"
    r"10(?:\.\d{1,3}){3}|"
    r"192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}"
    r")(?::\d+)?$"
)


def _csv_values(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    return [item.strip().strip("\"'") for item in raw_value.split(",") if item.strip().strip("\"'")]


def _get_cors_allowed_origins() -> str:
    values: list[str] = []
    for env_name in ("CORS_ALLOWED_ORIGINS", "CORS_ORIGINS"):
        values.extend(_csv_values(os.getenv(env_name)))
    if not values:
        values = ["http://localhost:3000", "http://127.0.0.1:3000"]
    return ",".join(dict.fromkeys(values))


def _get_cors_allowed_origin_regex() -> str | None:
    configured = os.getenv("CORS_ALLOWED_ORIGIN_REGEX")
    if configured is not None:
        return configured.strip().strip("\"'") or None

    environment = os.getenv("ENVIRONMENT", "local").lower()
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

    return "postgresql+psycopg2://postgres:postgres@localhost:5432/realestate"


class Settings(BaseModel):
    app_name: str = SystemMessages.APP_NAME
    environment: str = os.getenv("ENVIRONMENT", "local")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    database_url: str = _get_database_url()
    db_sslmode: str = os.getenv("DB_SSLMODE", "require")

    api_v1_prefix: str = SystemMessages.API_V1_PREFIX
    cors_allowed_origins: str = _get_cors_allowed_origins()
    cors_allowed_origin_regex: str | None = _get_cors_allowed_origin_regex()

    notification_email_mode: str = os.getenv("NOTIFICATION_EMAIL_MODE", "log")
    notification_sms_mode: str = os.getenv("NOTIFICATION_SMS_MODE", "log")
    notification_poll_interval_seconds: int = int(os.getenv("NOTIFICATION_POLL_INTERVAL_SECONDS", "30"))
    ses_from_email: str | None = os.getenv("SES_FROM_EMAIL")
    ses_from_name: str | None = os.getenv("SES_FROM_NAME")
    email_otp_verification_subject: str = os.getenv(
        "EMAIL_OTP_VERIFICATION_SUBJECT",
        "Verify your email address",
    )
    expose_otp_in_response: bool = os.getenv(
        "EXPOSE_OTP_IN_RESPONSE",
        "true" if os.getenv("ENVIRONMENT", "local").lower() in {"local", "development", "dev"} else "false",
    ).lower() == "true"
    supported_locales: str = os.getenv("SUPPORTED_LOCALES", "en,ar,fr,es")
    default_locale: str = os.getenv("DEFAULT_LOCALE", "en")
    auth_token_secret: str = os.getenv("AUTH_TOKEN_SECRET", os.getenv("SECRET_KEY", "abdoun-dev-token-secret"))
    auth_access_token_seconds: int = int(os.getenv("AUTH_ACCESS_TOKEN_SECONDS", "3600"))
    auth_refresh_token_seconds: int = int(os.getenv("AUTH_REFRESH_TOKEN_SECONDS", "604800"))
    auth_otp_ttl_seconds: int = int(os.getenv("AUTH_OTP_TTL_SECONDS", "600"))
    agency_invitation_ttl_seconds: int = int(os.getenv("AGENCY_INVITATION_TTL_SECONDS", "900"))
    agency_password_setup_ttl_seconds: int = int(os.getenv("AGENCY_PASSWORD_SETUP_TTL_SECONDS", "900"))
    agent_invitation_ttl_seconds: int = int(os.getenv("AGENT_INVITATION_TTL_SECONDS", "900"))
    frontend_base_url: str = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")
    allow_owner_multiple_agencies: bool = os.getenv("ALLOW_OWNER_MULTIPLE_AGENCIES", "false").lower() == "true"

    aws_s3_bucket: str | None = os.getenv("AWS_S3_BUCKET", "").strip().strip("\"'")
    aws_region: str = os.getenv("AWS_REGION", "us-west-2").strip().strip("\"'") or "us-west-2"
    aws_access_key_id: str | None = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str | None = os.getenv("AWS_SECRET_ACCESS_KEY")

    cognito_region: str = (
        os.getenv("COGNITO_REGION") or os.getenv("AWS_REGION") or "us-west-2"
    ).strip().strip("\"'") or "us-west-2"
    cognito_user_pool_id: str = os.getenv("COGNITO_USER_POOL_ID", "").strip().strip("\"'")
    cognito_app_client_id: str = os.getenv("COGNITO_APP_CLIENT_ID", "").strip().strip("\"'")
    cognito_app_client_secret: str = os.getenv("COGNITO_APP_CLIENT_SECRET", "").strip().strip("\"'")
    cognito_domain: str = os.getenv("COGNITO_DOMAIN", "").strip().strip("\"'")
    media_url_presign_enabled: bool = os.getenv("MEDIA_URL_PRESIGN_ENABLED", "true").lower() == "true"
    media_url_presign_expires_seconds: int = int(os.getenv("MEDIA_URL_PRESIGN_EXPIRES_SECONDS", "3600"))
    media_upload_presign_expires_seconds: int = int(os.getenv("MEDIA_UPLOAD_PRESIGN_EXPIRES_SECONDS", "900"))
    
    # Azure OpenAI settings (optional, for geocoding fallback)
    azure_openai_key: str | None = os.getenv("AZURE_OPENAI_KEY")
    azure_openai_endpoint: str | None = os.getenv("AZURE_ENDPOINT")
    azure_openai_api_version: str | None = os.getenv("AZURE_API_VERSION")
    azure_openai_deployment_name: str | None = os.getenv("AZURE_DEPLOYMENT_NAME")


@lru_cache
def get_settings() -> Settings:
    return Settings()
