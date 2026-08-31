"""Create Property built-up area unit handling."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.property_submissions import (
    create_submission,
    normalize_built_up_area_to_sqm,
    submit_submission,
    validate_built_up_area,
)


def test_draft_preserves_entered_sqft_value_and_unit() -> None:
    payload = {
        "property_details": {
            "built_up_area": 1234.56,
            "built_up_area_unit": "sqft",
        }
    }

    submission = create_submission(
        MagicMock(),
        user_id=uuid4(),
        agency_id=None,
        payload=payload,
        current_step=4,
        last_completed_step=3,
    )

    assert submission.payload["property_details"]["built_up_area"] == 1234.56
    assert submission.payload["property_details"]["built_up_area_unit"] == "sqft"


def test_submit_normalizes_sqft_to_sqm() -> None:
    payload = {
        "property_details": {
            "built_up_area": 1000,
            "built_up_area_unit": "sqft",
        }
    }

    normalized = normalize_built_up_area_to_sqm(payload)

    assert normalized["property_details"]["built_up_area"] == pytest.approx(92.90304)
    assert normalized["property_details"]["built_up_area_unit"] == "sqm"
    assert payload["property_details"] == {"built_up_area": 1000, "built_up_area_unit": "sqft"}


def test_existing_draft_is_normalized_when_submitted(monkeypatch) -> None:
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
            "property_details": {"built_up_area": 500, "built_up_area_unit": "sqft"},
            "media_documents": {"images": [{"url": "https://example.com/property.jpg"}]},
        },
    )

    submit_submission(MagicMock(), submission, user_id=submission.submitted_by, roles=())

    assert submission.payload["property_details"]["built_up_area"] == pytest.approx(46.45152)
    assert submission.payload["property_details"]["built_up_area_unit"] == "sqm"


def test_submit_keeps_sqm_value_unchanged() -> None:
    payload = {"property_details": {"built_up_area": 125.75, "built_up_area_unit": "sqm"}}

    normalized = normalize_built_up_area_to_sqm(payload)

    assert normalized["property_details"]["built_up_area"] == 125.75
    assert normalized["property_details"]["built_up_area_unit"] == "sqm"


def test_legacy_area_without_unit_is_treated_as_sqm() -> None:
    payload = {"property_details": {"built_up_area": 80}}

    normalized = normalize_built_up_area_to_sqm(payload)

    assert normalized["property_details"] == {"built_up_area": 80}


@pytest.mark.parametrize(
    ("value", "unit"),
    [
        (0, "sqm"),
        (-1, "sqft"),
        ("not-a-number", "sqm"),
        (10, "acre"),
    ],
)
def test_invalid_built_up_area_is_rejected(value: object, unit: str) -> None:
    with pytest.raises(HTTPException) as error:
        validate_built_up_area(
            {"property_details": {"built_up_area": value, "built_up_area_unit": unit}}
        )

    assert error.value.status_code == 400


def test_legacy_area_unit_key_is_supported() -> None:
    normalized = normalize_built_up_area_to_sqm(
        {"property_details": {"built_up_area": 100, "area_unit": "sqft"}}
    )

    assert normalized["property_details"]["built_up_area"] == pytest.approx(9.290304)
    assert normalized["property_details"]["area_unit"] == "sqm"
