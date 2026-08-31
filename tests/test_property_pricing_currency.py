"""Create Property pricing currency handling."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.property_submissions import (
    create_submission,
    normalize_pricing_to_jod,
    submit_submission,
    validate_pricing,
)


@pytest.fixture(autouse=True)
def _fixed_jod_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.exchange_rates.get_jod_exchange_rate",
        lambda from_currency: Decimal("0.709") if from_currency.upper() == "USD" else Decimal("1"),
    )


def test_draft_preserves_entered_amount_and_currency() -> None:
    payload = {
        "pricing": {
            "price": 250000,
            "currency": "USD",
            "service_charge": 120,
            "service_charge_currency": "GBP",
            "maintenance_fee": 50,
        }
    }

    submission = create_submission(
        MagicMock(),
        user_id=uuid4(),
        agency_id=None,
        payload=payload,
        current_step=5,
        last_completed_step=4,
    )

    pricing = submission.payload["pricing"]
    assert pricing["price"] == 250000
    assert pricing["currency"] == "USD"
    assert pricing["service_charge"] == 120
    assert pricing["service_charge_currency"] == "GBP"
    assert pricing["maintenance_fee"] == 50


def test_submit_normalizes_usd_pricing_to_jod() -> None:
    payload = {
        "pricing": {
            "price": 100,
            "currency": "USD",
            "service_charge": 10,
            "maintenance_fee": 5,
        }
    }

    normalized = normalize_pricing_to_jod(payload)

    assert normalized["pricing"]["price"] == pytest.approx(70.9)
    assert normalized["pricing"]["service_charge"] == pytest.approx(7.09)
    assert normalized["pricing"]["maintenance_fee"] == pytest.approx(3.545)
    assert normalized["pricing"]["currency"] == "JOD"
    assert "service_charge_currency" not in normalized["pricing"]
    assert payload["pricing"]["currency"] == "USD"


def test_existing_draft_is_normalized_when_submitted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.property_submissions.resolve_listing_agency_or_400", lambda *args: None)
    monkeypatch.setattr("app.services.property_submissions.assert_owner_agency_rule", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "app.services.property_submissions.record_owner_agency_mapping_for_submission",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr("app.services.property_submissions._next_status_on_submit", lambda *args, **kwargs: "submitted")
    monkeypatch.setattr("app.services.property_submissions.ensure_property_id_and_sync_media", lambda *args: uuid4())
    monkeypatch.setattr("app.services.property_submissions.notify_agency_admins_for_submission", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.property_submissions.flag_modified", lambda *args: None)
    submission = SimpleNamespace(
        id=uuid4(),
        submitted_by=uuid4(),
        agency_id=uuid4(),
        property_id=None,
        status="draft",
        submitted_at=None,
        step_completion={},
        payload={
            "pricing": {"price": 200, "currency": "USD"},
            "media_documents": {"images": [{"url": "https://example.com/property.jpg"}]},
        },
    )

    submit_submission(MagicMock(), submission, user_id=submission.submitted_by, roles=())

    assert submission.payload["pricing"]["price"] == pytest.approx(141.8)
    assert submission.payload["pricing"]["currency"] == "JOD"


def test_submit_keeps_jod_values_unchanged() -> None:
    payload = {"pricing": {"price": 125.75, "currency": "JOD", "service_charge": 10}}

    normalized = normalize_pricing_to_jod(payload)

    assert normalized["pricing"]["price"] == 125.75
    assert normalized["pricing"]["service_charge"] == 10
    assert normalized["pricing"]["currency"] == "JOD"


def test_default_currency_is_jod_when_missing() -> None:
    payload = {"pricing": {"price": 50000}}

    submission = create_submission(
        MagicMock(),
        user_id=uuid4(),
        agency_id=None,
        payload=payload,
        current_step=5,
        last_completed_step=4,
    )

    assert submission.payload["pricing"]["currency"] == "JOD"


@pytest.mark.parametrize("currency", ["EUR", "CAD"])
def test_unsupported_currency_is_rejected(currency: str) -> None:
    with pytest.raises(HTTPException) as error:
        validate_pricing({"pricing": {"price": 100, "currency": currency or None}})

    assert error.value.status_code == 400


@pytest.mark.parametrize("value", [-1, "not-a-number", True])
def test_invalid_pricing_amount_is_rejected(value: object) -> None:
    with pytest.raises(HTTPException) as error:
        validate_pricing({"pricing": {"price": value, "currency": "JOD"}})

    assert error.value.status_code == 400
