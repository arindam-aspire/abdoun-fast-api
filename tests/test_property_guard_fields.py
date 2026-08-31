"""Create Property owner and guard field coverage."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services import public_properties
from app.services.property_submissions import (
    create_submission,
    prepare_property_contact_fields,
    serialize_submission,
    submit_submission,
    update_submission,
)


def test_create_draft_removes_owner_address_and_persists_guard_fields() -> None:
    submission = create_submission(
        MagicMock(),
        user_id=uuid4(),
        agency_id=None,
        payload={
            "owner_information": {
                "owner_address": "retired",
                "owners": [{"full_name": "Owner", "owner_address": "retired", "address": "legacy"}],
            },
            "property_details": {
                "guard_name": "  Ahmad  ",
                "guard_phone_number": "+962 7 9000 0000",
            },
        },
        current_step=4,
        last_completed_step=3,
    )

    assert "owner_address" not in submission.payload["owner_information"]
    assert "owner_address" not in submission.payload["owner_information"]["owners"][0]
    assert submission.payload["owner_information"]["owners"][0]["address"] == "legacy"
    assert submission.payload["property_details"]["guard_name"] == "Ahmad"
    assert submission.payload["property_details"]["guard_phone_number"] == "+962790000000"


def test_update_draft_persists_guard_fields(monkeypatch) -> None:
    monkeypatch.setattr("app.services.property_submissions.flag_modified", lambda *args: None)
    submission = SimpleNamespace(
        id=uuid4(),
        status="draft",
        payload={},
        show_location=False,
        reference_number=None,
        agency_id=None,
        current_step=3,
        last_completed_step=2,
        step_completion={},
        property_id=None,
    )

    update_submission(
        MagicMock(),
        submission,
        agency_id=None,
        payload={
            "property_details": {
                "guard_name": "Omar",
                "guard_phone_number": "+962790000001",
            }
        },
        current_step=4,
        last_completed_step=4,
    )

    assert submission.payload["property_details"]["guard_name"] == "Omar"
    assert submission.payload["property_details"]["guard_phone_number"] == "+962790000001"


def test_draft_load_hides_legacy_owner_address_and_returns_guard_fields() -> None:
    submission = SimpleNamespace(
        id=uuid4(),
        submitted_by=uuid4(),
        agency_id=None,
        status="draft",
        current_step=4,
        last_completed_step=4,
        step_completion={},
        payload={
            "owner_information": {"owner_address": "retired"},
            "property_details": {
                "guard_name": "Ahmad",
                "guard_phone_number": "+962790000000",
            },
        },
        show_location=False,
        reference_number=None,
        reviewed_by=None,
        reviewed_at=None,
        review_reason=None,
    )

    payload = serialize_submission(submission)["payload"]

    assert "owner_address" not in payload["owner_information"]
    assert payload["property_details"]["guard_name"] == "Ahmad"
    assert payload["property_details"]["guard_phone_number"] == "+962790000000"


def test_final_submit_retains_guard_fields_and_removes_owner_address(monkeypatch) -> None:
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
            "owner_information": {"owner_address": "retired"},
            "property_details": {
                "guard_name": "Ahmad",
                "guard_phone_number": "+962790000000",
            },
            "media_documents": {"images": [{"url": "https://example.com/property.jpg"}]},
        },
    )

    submit_submission(MagicMock(), submission, user_id=submission.submitted_by, roles=())

    assert "owner_address" not in submission.payload["owner_information"]
    assert submission.payload["property_details"]["guard_name"] == "Ahmad"
    assert submission.payload["property_details"]["guard_phone_number"] == "+962790000000"


@pytest.mark.parametrize(
    "property_details",
    [
        {"guard_name": 123},
        {"guard_name": "x" * 256},
        {"guard_phone_number": "0790000000"},
    ],
)
def test_invalid_guard_fields_are_rejected(property_details: dict) -> None:
    with pytest.raises(HTTPException) as error:
        prepare_property_contact_fields({"property_details": property_details})

    assert error.value.status_code == 400


def test_authenticated_property_detail_returns_guard_fields(monkeypatch) -> None:
    listing = {
        "id": 1,
        "listing_type": "sale",
        "propertyType": "Apartment",
        "areaName": "Abdoun",
        "city": "Amman",
        "location": {"latitude": None, "longitude": None},
        "location_detail": {"latitude": None, "longitude": None},
        "show_location": False,
    }
    monkeypatch.setattr(public_properties, "serialize_property_listing", lambda *args, **kwargs: listing)
    monkeypatch.setattr(public_properties, "serialize_property_detail_workflow", lambda *args, **kwargs: {})
    monkeypatch.setattr(public_properties, "_agency_for_submission", lambda *args, **kwargs: None)
    monkeypatch.setattr(public_properties, "_load_property_media", lambda *args, **kwargs: [])
    monkeypatch.setattr(public_properties, "_media_for_details", lambda *args, **kwargs: {})
    monkeypatch.setattr(public_properties, "_feature_ids", lambda *args, **kwargs: [])
    monkeypatch.setattr(public_properties, "_feature_list", lambda *args, **kwargs: [])
    submission = SimpleNamespace(
        payload={
            "property_details": {
                "guard_name": "Ahmad",
                "guard_phone_number": "+962790000000",
            }
        },
        property_id=uuid4(),
        id=uuid4(),
        created_at=None,
        updated_at=None,
        reviewed_at=None,
    )

    detail = public_properties.serialize_property_detail(
        MagicMock(),
        submission,
        include_private_fields=True,
    )

    assert detail["guard_name"] == "Ahmad"
    assert detail["guard_phone_number"] == "+962790000000"
    assert detail["details"]["guard_name"] == "Ahmad"
    assert detail["details"]["guard_phone_number"] == "+962790000000"
