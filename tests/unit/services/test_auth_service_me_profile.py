"""Unit tests for GET /auth/me profile enrichment."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.schemas.user import RoleResponse
from app.services.auth_service import AuthService
from app.utils.constants import UserRoles


def _service() -> AuthService:
    return AuthService(MagicMock())


def test_user_has_linked_agency_false_without_agency_id() -> None:
    user = SimpleNamespace(agency_id=None, agency=None)
    assert AuthService._user_has_linked_agency(user) is False


def test_user_has_linked_agency_false_when_id_set_but_row_missing() -> None:
    user = SimpleNamespace(agency_id=uuid.uuid4(), agency=None)
    assert AuthService._user_has_linked_agency(user) is False


def test_user_has_linked_agency_true_when_agency_linked() -> None:
    agency_id = uuid.uuid4()
    agency = SimpleNamespace(id=agency_id, agency_name="Acme Realty")
    user = SimpleNamespace(agency_id=agency_id, agency=agency)
    assert AuthService._user_has_linked_agency(user, agency=agency) is True


def test_get_current_user_profile_sets_has_agency_for_owner_with_agency() -> None:
    service = _service()
    agency_id = uuid.uuid4()
    agency = SimpleNamespace(
        id=agency_id,
        agency_name="Owner Agency",
        agency_trade_name="Owner Trade",
        email="owner@example.com",
        phone="+962790000000",
        website=None,
        currency="JOD",
        measurement_unit="sqm",
    )
    user = SimpleNamespace(
        id=uuid.uuid4(),
        email="owner@example.com",
        full_name="Property Owner",
        phone_number="+962790000000",
        is_active=True,
        is_email_verified=True,
        is_phone_verified=False,
        profile_picture_url=None,
        agency_id=agency_id,
        agency=agency,
        roles=[SimpleNamespace(id=uuid.uuid4(), name=UserRoles.OWNER, description=None, permissions=[], created_at=datetime.now(timezone.utc))],
        created_at=datetime.now(timezone.utc),
        deleted_at=None,
        deleted_by=None,
        profile=None,
    )

    response = service.get_current_user_profile(user)
    assert response.data is not None
    assert response.data.has_agency is True
    assert response.data.agency is not None
    assert response.data.agency.agency_id == agency_id


def test_get_current_user_profile_sets_has_agency_false_for_owner_without_agency() -> None:
    service = _service()
    user = SimpleNamespace(
        id=uuid.uuid4(),
        email="owner2@example.com",
        full_name="Owner No Agency",
        phone_number=None,
        is_active=True,
        is_email_verified=True,
        is_phone_verified=False,
        profile_picture_url=None,
        agency_id=None,
        agency=None,
        roles=[SimpleNamespace(id=uuid.uuid4(), name=UserRoles.OWNER, description=None, permissions=[], created_at=datetime.now(timezone.utc))],
        created_at=datetime.now(timezone.utc),
        deleted_at=None,
        deleted_by=None,
        profile=None,
    )

    response = service.get_current_user_profile(user)
    assert response.data is not None
    assert response.data.has_agency is False
    assert response.data.agency is None
