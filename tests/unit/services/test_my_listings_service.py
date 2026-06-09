"""Unit tests for MyListingsService."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.my_listings_service import MyListingsService
from app.utils.constants import ErrorMessages


@pytest.fixture
def mock_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(mock_repo: MagicMock) -> MyListingsService:
    return MyListingsService(property_repository=mock_repo)


def _property_row(**overrides):
    defaults = {
        "id": uuid.uuid4(),
        "property_hash": 123456789,
        "title": "Villa in Abdoun",
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 2, 1, tzinfo=timezone.utc),
        "created_by": uuid.uuid4(),
        "type": SimpleNamespace(slug="villa"),
        "property_status": SimpleNamespace(slug="verified"),
        "agent_user": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_list_my_listings_agent_scope_calls_repo_with_user_id(
    service: MyListingsService, mock_repo: MagicMock
) -> None:
    user_id = uuid.uuid4()
    prop = _property_row()
    mock_repo.list_my_listings.return_value = ([prop], 1, {})

    result = service.list_my_listings(
        scope="agent",
        user_id=user_id,
        page=1,
        page_size=10,
    )

    mock_repo.list_my_listings.assert_called_once_with(
        scope="agent",
        agent_user_id=user_id,
        page=1,
        page_size=10,
        status=None,
        property_type=None,
        search=None,
    )
    assert result.total_count == 1
    assert result.items[0].property_hash_id == 123456789
    assert result.items[0].status == "Active"
    assert result.items[0].agent is None


def test_list_my_listings_admin_includes_assigned_agent(
    service: MyListingsService, mock_repo: MagicMock
) -> None:
    agent_id = uuid.uuid4()
    prop = _property_row(
        agent_user=SimpleNamespace(
            id=agent_id,
            full_name="Agent One",
            email="agent@example.com",
            phone_number="+962790000000",
        )
    )
    mock_repo.list_my_listings.return_value = ([prop], 1, {})

    result = service.list_my_listings(
        scope="admin",
        user_id=uuid.uuid4(),
        page=1,
        page_size=20,
    )

    assert mock_repo.list_my_listings.call_args.kwargs["agent_user_id"] is None
    assert result.items[0].agent is not None
    assert result.items[0].agent.id == agent_id
    assert result.items[0].agent.full_name == "Agent One"


def test_list_my_listings_rejects_invalid_status_filter(
    service: MyListingsService, mock_repo: MagicMock
) -> None:
    with pytest.raises(HTTPException) as exc:
        service.list_my_listings(
            scope="admin",
            user_id=uuid.uuid4(),
            page=1,
            page_size=10,
            status="unknown",
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == ErrorMessages.INVALID_MY_LISTING_STATUS_FILTER
    mock_repo.list_my_listings.assert_not_called()


def test_list_my_listings_passes_filters_to_repo(
    service: MyListingsService, mock_repo: MagicMock
) -> None:
    mock_repo.list_my_listings.return_value = ([], 0, {})
    service.list_my_listings(
        scope="admin",
        user_id=uuid.uuid4(),
        page=2,
        page_size=5,
        status="pending",
        property_type="apartment",
        search="abdoun",
    )
    mock_repo.list_my_listings.assert_called_once_with(
        scope="admin",
        agent_user_id=None,
        page=2,
        page_size=5,
        status="pending",
        property_type="apartment",
        search="abdoun",
    )
