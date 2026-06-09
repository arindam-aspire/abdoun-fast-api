"""Unit tests for RecentViewService."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.schemas.recent_view import RecentViewUpsertRequest
from app.services.recent_view_service import RecentViewService
from app.utils.constants import ErrorMessages


@pytest.fixture
def mock_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(mock_repo: MagicMock) -> RecentViewService:
    return RecentViewService(mock_repo)


def test_add_or_refresh_from_request_uses_property_id(
    service: RecentViewService, mock_repo: MagicMock
) -> None:
    user_id = uuid.uuid4()
    property_id = uuid.uuid4()
    mock_repo.resolve_property_id.return_value = property_id
    mock_repo.ensure_user_exists_and_lock.return_value = True
    mock_repo.property_exists.return_value = True

    service.add_or_refresh_from_request(
        user_id=user_id,
        body=RecentViewUpsertRequest(property_id=property_id),
    )

    mock_repo.resolve_property_id.assert_called_once_with(
        property_id=property_id,
        property_hash_id=None,
    )
    mock_repo.upsert_recent_view.assert_called_once_with(user_id=user_id, property_id=property_id)
    mock_repo.commit.assert_called_once()


def test_add_or_refresh_from_request_resolves_property_hash_id(
    service: RecentViewService, mock_repo: MagicMock
) -> None:
    user_id = uuid.uuid4()
    property_id = uuid.uuid4()
    mock_repo.resolve_property_id.return_value = property_id
    mock_repo.ensure_user_exists_and_lock.return_value = True
    mock_repo.property_exists.return_value = True

    service.add_or_refresh_from_request(
        user_id=user_id,
        body=RecentViewUpsertRequest(property_hash_id=123456789),
    )

    mock_repo.resolve_property_id.assert_called_once_with(
        property_id=None,
        property_hash_id=123456789,
    )
    mock_repo.upsert_recent_view.assert_called_once_with(user_id=user_id, property_id=property_id)


def test_add_or_refresh_from_request_prioritizes_property_id_when_both_sent(
    service: RecentViewService, mock_repo: MagicMock
) -> None:
    user_id = uuid.uuid4()
    property_id = uuid.uuid4()
    other_id = uuid.uuid4()
    mock_repo.resolve_property_id.return_value = property_id
    mock_repo.ensure_user_exists_and_lock.return_value = True
    mock_repo.property_exists.return_value = True

    service.add_or_refresh_from_request(
        user_id=user_id,
        body=RecentViewUpsertRequest(property_id=property_id, property_hash_id=999),
    )

    mock_repo.resolve_property_id.assert_called_once_with(
        property_id=property_id,
        property_hash_id=999,
    )
    mock_repo.upsert_recent_view.assert_called_once_with(user_id=user_id, property_id=property_id)
    assert mock_repo.find_property_uuid_by_hash.call_count == 0 or mock_repo.resolve_property_id.return_value == property_id


def test_add_or_refresh_from_request_404_when_hash_not_found(
    service: RecentViewService, mock_repo: MagicMock
) -> None:
    user_id = uuid.uuid4()
    mock_repo.resolve_property_id.return_value = None

    with pytest.raises(HTTPException) as exc:
        service.add_or_refresh_from_request(
            user_id=user_id,
            body=RecentViewUpsertRequest(property_hash_id=404404404),
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == ErrorMessages.PROPERTY_NOT_FOUND
    mock_repo.upsert_recent_view.assert_not_called()


def test_add_or_refresh_from_request_404_when_property_id_missing_in_db(
    service: RecentViewService, mock_repo: MagicMock
) -> None:
    user_id = uuid.uuid4()
    property_id = uuid.uuid4()
    mock_repo.resolve_property_id.return_value = property_id
    mock_repo.ensure_user_exists_and_lock.return_value = True
    mock_repo.property_exists.return_value = False

    with pytest.raises(HTTPException) as exc:
        service.add_or_refresh_from_request(
            user_id=user_id,
            body=RecentViewUpsertRequest(property_id=property_id),
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == ErrorMessages.PROPERTY_NOT_FOUND
