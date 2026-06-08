"""Tests for nested PropertyAgencyInfo currency/measurement_unit."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from app.schemas.property import PropertyAgencyInfo, _agency_config_from_orm, _user_to_agency_payload


def test_agency_config_from_orm_uses_defaults() -> None:
    agency = MagicMock()
    agency.currency = None
    agency.measurement_unit = None
    assert _agency_config_from_orm(agency) == ("JOD", "sqm")


def test_user_to_agency_payload_includes_config() -> None:
    agency_id = uuid4()
    agency = MagicMock()
    agency.id = agency_id
    agency.agency_name = "A"
    agency.agency_trade_name = "A"
    agency.email = "a@b.com"
    agency.phone = "+12025551234"
    agency.website = None
    agency.currency = "USD"
    agency.measurement_unit = "sqft"
    user = MagicMock()
    user.agency = agency
    user.profile_picture_url = None

    info = _user_to_agency_payload(user)
    assert isinstance(info, PropertyAgencyInfo)
    assert info.currency == "USD"
    assert info.measurement_unit == "sqft"
