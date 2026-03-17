from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import get_settings

settings = get_settings()

def _build_engine_kwargs(database_url: str) -> dict:
    # SQLite (used in tests/local) doesn't use these pool settings consistently.
    if database_url.startswith("sqlite"):
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

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
