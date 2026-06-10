"""Unit tests for owner agency linking service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.owner_agency_link_service import OwnerAgencyLinkService
from app.utils.constants import ErrorMessages, SuccessMessages, UserRoles


def _service() -> tuple[OwnerAgencyLinkService, MagicMock, MagicMock]:
    user_repo = MagicMock()
    agency_repo = MagicMock()
    return OwnerAgencyLinkService(user_repo, agency_repo), user_repo, agency_repo


def _agency(agency_id: uuid.UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=agency_id or uuid.uuid4(),
        agency_name="Acme Realty",
        agency_trade_name="Acme Trade",
        legal_document_s3_link="https://example.com/doc.pdf",
        logo_url=None,
        email="agency@example.com",
        phone="+962790000001",
        website=None,
        address=None,
        city=None,
        state=None,
        country=None,
        zip_code=None,
        currency="JOD",
        measurement_unit="sqm",
        is_active=True,
        is_verified=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _owner(*, agency_id: uuid.UUID | None = None) -> MagicMock:
    user = MagicMock()
    user.agency_id = agency_id
    role = MagicMock()
    role.name = UserRoles.OWNER
    user.roles = [role]
    return user


def test_link_agency_returns_existing_when_already_linked() -> None:
    service, user_repo, agency_repo = _service()
    linked_id = uuid.uuid4()
    owner = _owner(agency_id=linked_id)
    existing = _agency(linked_id)
    agency_repo.get_by_id.return_value = existing
    agency_repo.get_profile_picture_map_for_agencies.return_value = {}

    response = service.link_agency(current_user=owner, agency_id=uuid.uuid4())

    assert response.success is True
    assert response.message == SuccessMessages.AGENCY_ALREADY_LINKED_TO_OWNER
    assert response.data is not None
    assert response.data.id == linked_id
    user_repo.set_user_agency_id.assert_not_called()
    user_repo.commit.assert_not_called()
    agency_repo.get_by_id.assert_called_once_with(linked_id)


def test_link_agency_links_when_owner_has_no_agency() -> None:
    service, user_repo, agency_repo = _service()
    owner = _owner(agency_id=None)
    target_id = uuid.uuid4()
    target = _agency(target_id)
    agency_repo.get_by_id.return_value = target
    agency_repo.get_profile_picture_map_for_agencies.return_value = {}

    response = service.link_agency(current_user=owner, agency_id=target_id)

    assert response.success is True
    assert response.message == SuccessMessages.AGENCY_LINKED_SUCCESSFULLY
    assert response.data is not None
    assert response.data.id == target_id
    user_repo.set_user_agency_id.assert_called_once_with(user=owner, agency_id=target_id)
    user_repo.commit.assert_called_once()


def test_link_agency_404_when_agency_missing() -> None:
    service, user_repo, agency_repo = _service()
    owner = _owner(agency_id=None)
    missing_id = uuid.uuid4()
    agency_repo.get_by_id.return_value = None

    with pytest.raises(HTTPException) as exc:
        service.link_agency(current_user=owner, agency_id=missing_id)

    assert exc.value.status_code == 404
    assert exc.value.detail == ErrorMessages.AGENCY_NOT_FOUND
    user_repo.set_user_agency_id.assert_not_called()


def test_link_agency_repairs_orphaned_agency_id() -> None:
    service, user_repo, agency_repo = _service()
    orphaned_id = uuid.uuid4()
    owner = _owner(agency_id=orphaned_id)
    new_id = uuid.uuid4()
    new_agency = _agency(new_id)

    def _get_by_id(agency_id: uuid.UUID):
        if agency_id == orphaned_id:
            return None
        if agency_id == new_id:
            return new_agency
        return None

    agency_repo.get_by_id.side_effect = _get_by_id
    agency_repo.get_profile_picture_map_for_agencies.return_value = {}

    response = service.link_agency(current_user=owner, agency_id=new_id)

    assert response.message == SuccessMessages.AGENCY_LINKED_SUCCESSFULLY
    user_repo.set_user_agency_id.assert_called_once_with(user=owner, agency_id=new_id)
