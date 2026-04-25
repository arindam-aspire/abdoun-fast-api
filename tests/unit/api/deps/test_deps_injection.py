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
from app.api.v1.deps.media_urls import get_media_url_signer
from app.api.v1.deps.profile_picture_upload import (
    get_auth_repository_for_upload,
    get_profile_picture_upload_service,
)
from app.api.v1.deps.uploads import (
    get_s3_service,
    get_upload_repository,
    get_upload_service,
)
from app.api.v1.deps.auth import get_profile_update_service
from app.api.v1.deps.property_submissions import (
    get_property_submission_repository,
    get_property_submission_service,
)
from app.api.v1.deps.users import get_user_repository, get_user_service
from app.repositories.agent_repository import AgentRepository
from app.repositories.auth_repository import AuthRepository
from app.repositories.agent_dashboard_repository import AgentDashboardRepository
from app.repositories.property_repository import PropertyRepository
from app.repositories.property_submission_repository import PropertySubmissionRepository
from app.repositories.user_repository import UserRepository
from app.services.agent_service import AgentService
from app.services.agent_dashboard_service import AgentDashboardService
from app.services.geo_search_service import GeoSearchService
from app.services.property_import_service import PropertyImportService
from app.services.property_submission_service import PropertySubmissionService
from app.services.user_service import UserService
from app.services.s3_service import S3Service
from app.services.profile_picture_upload_service import ProfilePictureUploadService
from app.services.upload_service import UploadService
from app.services.profile_update_service import ProfileUpdateService


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


def test_get_property_submission_repository_returns_repo(mock_db: MagicMock) -> None:
    repo = get_property_submission_repository(mock_db)
    assert isinstance(repo, PropertySubmissionRepository)


def test_get_property_submission_service_returns_service(mock_db: MagicMock) -> None:
    repo = PropertySubmissionRepository(mock_db)
    svc = get_property_submission_service(repo=repo)
    assert isinstance(svc, PropertySubmissionService)


def test_get_upload_repository_returns_property_submission_repo(mock_db: MagicMock) -> None:
    repo = get_upload_repository(mock_db)
    assert isinstance(repo, PropertySubmissionRepository)


def test_get_s3_service_returns_s3_service() -> None:
    svc = get_s3_service()
    assert isinstance(svc, S3Service)


def test_get_upload_service_returns_upload_service(mock_db: MagicMock) -> None:
    repo = PropertySubmissionRepository(mock_db)
    s3 = S3Service()
    svc = get_upload_service(repo=repo, s3_service=s3)
    assert isinstance(svc, UploadService)


def test_get_profile_update_service_returns_service(mock_db: MagicMock) -> None:
    svc = get_profile_update_service(mock_db)
    assert isinstance(svc, ProfileUpdateService)


def test_get_auth_repository_for_upload_returns_auth_repository(mock_db: MagicMock) -> None:
    repo = get_auth_repository_for_upload(mock_db)
    assert isinstance(repo, AuthRepository)
    assert repo._db is mock_db


def test_get_profile_picture_upload_service_returns_service(mock_db: MagicMock) -> None:
    repo = AuthRepository(mock_db)
    s3 = S3Service()
    svc = get_profile_picture_upload_service(repo=repo, s3_service=s3)
    assert isinstance(svc, ProfilePictureUploadService)


def test_get_media_url_signer_returns_signer() -> None:
    s3 = S3Service()
    signer = get_media_url_signer(s3=s3)
    from app.services.media_url_signer import MediaUrlSigner

    assert isinstance(signer, MediaUrlSigner)
