"""Unit tests for API dependency injection (get_*_repository, get_*_service)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.api.v1.deps.agents import get_agent_repository, get_agent_service
from app.api.v1.deps.agent_dashboard import (
    get_agent_dashboard_repository,
    get_agent_dashboard_service,
)
from app.api.v1.deps.search import (
    get_geo_search_service,
    get_property_import_service,
    get_search_property_repository,
)
from app.api.v1.deps.users import get_user_repository, get_user_service
from app.repositories.agent_repository import AgentRepository
from app.repositories.agent_dashboard_repository import AgentDashboardRepository
from app.repositories.property_repository import PropertyRepository
from app.repositories.user_repository import UserRepository
from app.services.agent_service import AgentService
from app.services.agent_dashboard_service import AgentDashboardService
from app.services.geo_search_service import GeoSearchService
from app.services.property_import_service import PropertyImportService
from app.services.user_service import UserService


@pytest.fixture
def mock_db():
    return MagicMock()


def test_get_agent_repository_returns_agent_repository(mock_db: MagicMock) -> None:
    repo = get_agent_repository(mock_db)
    assert isinstance(repo, AgentRepository)
    assert repo._db is mock_db


def test_get_agent_service_returns_agent_service(mock_db: MagicMock) -> None:
    repo = AgentRepository(mock_db)
    svc = get_agent_service(repo=repo)
    assert isinstance(svc, AgentService)


def test_get_agent_dashboard_repository_returns_repository(mock_db: MagicMock) -> None:
    repo = get_agent_dashboard_repository(mock_db)
    assert isinstance(repo, AgentDashboardRepository)
    assert repo._db is mock_db


def test_get_agent_dashboard_service_returns_service(mock_db: MagicMock) -> None:
    repo = AgentDashboardRepository(mock_db)
    svc = get_agent_dashboard_service(repo=repo)
    assert isinstance(svc, AgentDashboardService)


def test_get_search_property_repository_returns_property_repository(mock_db: MagicMock) -> None:
    repo = get_search_property_repository(mock_db)
    assert isinstance(repo, PropertyRepository)


def test_get_geo_search_service_returns_geo_search_service(mock_db: MagicMock) -> None:
    repo = PropertyRepository(mock_db)
    svc = get_geo_search_service(repo=repo)
    assert isinstance(svc, GeoSearchService)


def test_get_property_import_service_returns_service(mock_db: MagicMock) -> None:
    svc = get_property_import_service(mock_db)
    assert isinstance(svc, PropertyImportService)


def test_get_user_repository_returns_user_repository(mock_db: MagicMock) -> None:
    repo = get_user_repository(mock_db)
    assert isinstance(repo, UserRepository)


def test_get_user_service_returns_user_service(mock_db: MagicMock) -> None:
    repo = UserRepository(mock_db)
    svc = get_user_service(repo=repo)
    assert isinstance(svc, UserService)
