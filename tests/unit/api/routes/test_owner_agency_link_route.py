"""Route tests for PATCH /users/agency."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.v1.deps.owner_agency_link import get_owner_agency_link_service
from app.core.auth import get_current_user
from app.db.session import get_db
from app.main import app
from app.schemas.agency import AgencyResponse
from app.utils.constants import SuccessMessages, UserRoles
from app.utils.responses import create_success_response


def _user(role_name: str, *, agency_id: uuid.UUID | None = None):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.agency_id = agency_id
    role = MagicMock()
    role.name = role_name
    role.permissions = []
    user.roles = [role]
    return user


def _fake_db():
    db = MagicMock()
    exec_result = MagicMock()
    exec_result.scalars.return_value.all.return_value = []
    db.execute.return_value = exec_result
    try:
        yield db
    finally:
        pass


def _agency_response(agency_id: uuid.UUID) -> AgencyResponse:
    now = datetime.now(timezone.utc)
    return AgencyResponse(
        id=agency_id,
        agency_name="Acme Realty",
        agency_trade_name="Acme Trade",
        legal_document_s3_link="https://example.com/doc.pdf",
        email="agency@example.com",
        phone="+962790000001",
        currency="JOD",
        measurement_unit="sqm",
        is_active=True,
        is_verified=False,
        created_at=now,
        updated_at=now,
    )


def test_link_owner_agency_route_success() -> None:
    agency_id = uuid.uuid4()
    service = MagicMock()
    service.link_agency.return_value = create_success_response(
        data=_agency_response(agency_id),
        message=SuccessMessages.AGENCY_LINKED_SUCCESSFULLY,
    )
    app.dependency_overrides[get_current_user] = lambda: _user(UserRoles.OWNER)
    app.dependency_overrides[get_owner_agency_link_service] = lambda: service
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    res = client.patch("/api/v1/users/agency", json={"agencyId": str(agency_id)})
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["message"] == SuccessMessages.AGENCY_LINKED_SUCCESSFULLY
    assert body["data"]["id"] == str(agency_id)
    service.link_agency.assert_called_once()
    app.dependency_overrides.clear()


def test_link_owner_agency_route_forbidden_for_non_owner() -> None:
    app.dependency_overrides[get_current_user] = lambda: _user(UserRoles.ADMIN)
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    res = client.patch("/api/v1/users/agency", json={"agencyId": str(uuid.uuid4())})
    assert res.status_code == 403
    app.dependency_overrides.clear()


def test_link_owner_agency_route_validates_agency_id() -> None:
    app.dependency_overrides[get_current_user] = lambda: _user(UserRoles.OWNER)
    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    res = client.patch("/api/v1/users/agency", json={})
    assert res.status_code == 422
    app.dependency_overrides.clear()
