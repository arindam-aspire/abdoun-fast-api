"""
Pytest fixtures for API and architecture validation tests.
Step 2 (capture before behaviour) and Steps 12-15 use this.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Shared TestClient for API contract and smoke tests."""
    return TestClient(app)


@pytest.fixture(scope="session")
def db_available() -> bool:
    """True if PostgreSQL is reachable (for skipping DB-dependent contract tests)."""
    try:
        from app.core.config import get_settings
        from sqlalchemy import create_engine
        engine = create_engine(get_settings().database_url)
        with engine.connect():
            pass
        return True
    except Exception:
        return False
