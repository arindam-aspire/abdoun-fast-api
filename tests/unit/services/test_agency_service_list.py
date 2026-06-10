"""Unit tests for agency list authorization."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.agency_service import AgencyService
from app.utils.constants import ErrorMessages, UserRoles


def _service() -> tuple[AgencyService, MagicMock]:
    repo = MagicMock()
    return AgencyService(repo, s3_service=MagicMock()), repo


def _user(role_name: str, *, agency_id: uuid.UUID | None = None) -> SimpleNamespace:
    role = SimpleNamespace(name=role_name)
    return SimpleNamespace(roles=[role], agency_id=agency_id)


def _agency_row() -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid.uuid4(),
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
        created_at=now,
        updated_at=now,
    )


def test_list_agencies_allows_owner_to_view_all() -> None:
    service, repo = _service()
    rows = [_agency_row(), _agency_row()]
    repo.list_agencies.return_value = rows
    repo.get_profile_picture_map_for_agencies.return_value = {}

    response = service.list_agencies(current_user=_user(UserRoles.OWNER), skip=0, limit=50)

    assert response.success is True
    assert response.data is not None
    assert len(response.data) == 2
    repo.list_agencies.assert_called_once_with(skip=0, limit=50)


def test_list_agencies_forbidden_for_agent() -> None:
    service, repo = _service()

    with pytest.raises(HTTPException) as exc:
        service.list_agencies(current_user=_user(UserRoles.AGENT), skip=0, limit=50)

    assert exc.value.status_code == 403
    assert exc.value.detail == ErrorMessages.AGENCY_ACCESS_DENIED
    repo.list_agencies.assert_not_called()
