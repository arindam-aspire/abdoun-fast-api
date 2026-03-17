"""
Step 15: Validate no DB access in routers.
Ensures no get_db, Session, or raw SQLAlchemy in route modules.
"""
from pathlib import Path

import pytest

ROUTE_DIR = Path(__file__).resolve().parent.parent.parent / "app" / "api" / "v1" / "routes"


def _read_route_file(module_name: str) -> str:
    path = ROUTE_DIR / f"{module_name}.py"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def test_agents_router_does_not_import_get_db():
    """Agents router must not use get_db (fully refactored to service layer)."""
    content = _read_route_file("agents")
    assert "get_db" not in content
    assert "from app.db" not in content


def test_users_router_does_not_import_get_db():
    """Users router must not use get_db (uses UserService only)."""
    content = _read_route_file("users")
    assert "get_db" not in content
    assert "from app.db" not in content


def test_agents_router_has_no_raw_session_or_commit():
    """Step 15: agents router must not contain Session, commit, or rollback."""
    content = _read_route_file("agents")
    assert "Session = Depends" not in content
    assert "db.commit()" not in content
    assert "db.rollback()" not in content
    assert "select(" not in content
    assert "from sqlalchemy" not in content


def test_auth_router_does_not_import_get_db():
    """Auth router must not use get_db (session provided via AuthService deps)."""
    content = _read_route_file("auth")
    assert "get_db" not in content
    assert "from app.db" not in content


def test_auth_router_has_no_session_or_sqlalchemy():
    """Auth router must not contain Session, commit, rollback, or raw SQLAlchemy."""
    content = _read_route_file("auth")
    assert "Session = Depends" not in content
    assert "db.commit()" not in content
    assert "db.rollback()" not in content
    assert "from sqlalchemy" not in content


def test_locations_router_does_not_import_get_db():
    """Locations router must not use get_db (uses LocationService only)."""
    content = _read_route_file("locations")
    assert "get_db" not in content
    assert "from app.db" not in content


def test_properties_router_does_not_import_get_db():
    """Properties router must not use get_db (session via PropertySearchService deps)."""
    content = _read_route_file("properties")
    assert "get_db" not in content
    assert "from app.db" not in content


def test_properties_router_has_no_session_or_sqlalchemy():
    """Properties router must not contain Session, DBSessionDep, or raw SQLAlchemy."""
    content = _read_route_file("properties")
    assert "Session = Depends" not in content
    assert "DBSessionDep" not in content
    assert "from sqlalchemy" not in content


def test_search_router_does_not_import_get_db():
    """Search router must not use get_db (uses GeoSearchService and PropertyImportService only)."""
    content = _read_route_file("search")
    assert "get_db" not in content
    assert "from app.db" not in content
