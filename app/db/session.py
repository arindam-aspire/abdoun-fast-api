"""Database engine and session lifecycle; provides get_db for request-scoped sessions."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import get_settings
from app.utils.constants import DbConstants
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.logger import api_logger

settings = get_settings()


def _build_engine_kwargs(database_url: str) -> dict:
    """Build keyword arguments for create_engine; SQLite gets only future=True, others use pool settings from config.

    Args:
        database_url: The database URL (e.g. postgresql+psycopg2://... or sqlite:///...).

    Returns:
        Dict of keyword arguments for sqlalchemy.create_engine.
    """
    if database_url.startswith(DbConstants.SQLITE_URL_PREFIX):
        return {"future": True}
    return {
        "future": True,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout,
        "pool_recycle": settings.db_pool_recycle,
        "pool_pre_ping": settings.db_pool_pre_ping,
    }


engine = create_engine(settings.database_url, **_build_engine_kwargs(settings.database_url))

try:
    from app.observability.slow_queries import install_slow_query_logging

    install_slow_query_logging(engine=engine, threshold_ms=settings.slow_query_threshold_ms)
except ImportError:  # pragma: no cover - optional dependency/module
    pass
except Exception as exc:  # pragma: no cover - import-time; must not break startup
    api_logger.warning(
        format_log_message(LogMessages.Database.SLOW_QUERY_LOGGING_INSTALL_FAILED, error=str(exc))
    )

if settings.otel_enabled:  # pragma: no cover - optional OTEL instrumentation at startup
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument(engine=engine)
    except ImportError:  # pragma: no cover - optional dependency
        pass
    except Exception as exc:  # pragma: no cover - must not break startup
        api_logger.warning(
            format_log_message(LogMessages.Database.OTEL_INSTRUMENTATION_FAILED, error=str(exc))
        )

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """Provide a request-scoped database session (FastAPI dependency).

    Yields:
        Session: Request-scoped SQLAlchemy Session; use via Depends(get_db).
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
