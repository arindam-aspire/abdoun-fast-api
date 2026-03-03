import os
from functools import lru_cache

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


class Settings(BaseModel):
    app_name: str = SystemMessages.APP_NAME
    environment: str = os.getenv("ENVIRONMENT", "local")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    database_url: str = _get_database_url()

    api_v1_prefix: str = SystemMessages.API_V1_PREFIX

    cors_origins: list[str] = _parse_csv_env(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    cors_allow_credentials: bool = os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"
    cors_allow_methods: list[str] = _parse_csv_env("CORS_ALLOW_METHODS", "*")
    cors_allow_headers: list[str] = _parse_csv_env("CORS_ALLOW_HEADERS", "*")
    
    # Azure OpenAI settings (optional, for geocoding fallback)
    azure_openai_key: str | None = os.getenv("AZURE_OPENAI_KEY")
    azure_openai_endpoint: str | None = os.getenv("AZURE_ENDPOINT")
    azure_openai_api_version: str | None = os.getenv("AZURE_API_VERSION")
    azure_openai_deployment_name: str | None = os.getenv("AZURE_DEPLOYMENT_NAME")


@lru_cache
def get_settings() -> Settings:
    return Settings()
