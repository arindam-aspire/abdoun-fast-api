"""Check the FastAPI application's actual database connection path safely."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import engine


def main() -> int:
    try:
        with engine.connect() as connection:
            db_name = connection.execute(text("select current_database()")).scalar()
    except SQLAlchemyError as exc:
        print("app-db-connection-failed")
        print(exc.__class__.__name__)
        print("Application database connection failed; verify DATABASE_URL or central DB settings.")
        return 1

    print("app-db-connection-ok")
    print(f"database={db_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
