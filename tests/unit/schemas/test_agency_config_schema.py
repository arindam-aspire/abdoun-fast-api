"""Tests for agency currency and measurement_unit schema validation."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.schemas.agency import AgencyResponse, AgencyUpdateRequest


def test_agency_response_includes_currency_and_measurement_unit() -> None:
    agency_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    resp = AgencyResponse(
        id=agency_id,
        agency_name="Test Agency",
        agency_trade_name="Test",
        legal_document_s3_link="https://example.com/doc.pdf",
        email="agency@example.com",
        phone="+12025551234",
        currency="JOD",
        measurement_unit="sqm",
        is_active=True,
        is_verified=False,
        created_at=now,
        updated_at=now,
    )
    assert resp.currency == "JOD"
    assert resp.measurement_unit == "sqm"


def test_update_request_normalizes_currency() -> None:
    body = AgencyUpdateRequest(currency="jod")
    assert body.currency == "JOD"


def test_update_request_rejects_invalid_measurement_unit() -> None:
    with pytest.raises(ValueError, match="measurement_unit"):
        AgencyUpdateRequest(measurement_unit="meters")
