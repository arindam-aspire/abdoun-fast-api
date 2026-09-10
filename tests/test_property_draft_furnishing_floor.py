"""Create/update/fetch coverage for Add Property furnishing status and floor."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.schemas.property_submissions import (
    PropertySubmissionCreateRequest,
    PropertySubmissionUpdateRequest,
)
from app.services.property_submissions import (
    create_submission,
    serialize_submission,
    update_submission,
)


def _resolve_option(_db, *, group, value, field):
    catalog = {
        ("furnishing_status", 21): SimpleNamespace(id=21, slug="furnished", name="Furnished", numeric_value=None),
        ("furnishing_status", 22): SimpleNamespace(
            id=22, slug="semi-furnished", name="Semi-Furnished", numeric_value=None
        ),
        ("floor", 5): SimpleNamespace(id=5, slug="3", name="Third", numeric_value=3),
        ("floor", 8): SimpleNamespace(id=8, slug="6", name="Sixth", numeric_value=6),
    }
    if isinstance(value, int) or (isinstance(value, str) and str(value).isdigit()):
        numeric = int(value)
        if (group, numeric) in catalog:
            return catalog[(group, numeric)]
        for (option_group, _id), option in catalog.items():
            if option_group == group and option.numeric_value == numeric:
                return option
    matches = [option for (option_group, _id), option in catalog.items() if option_group == group]
    token = str(value).strip().casefold().replace("_", "-").replace(" ", "-")
    for option in matches:
        if option.slug == token or option.name.casefold() == str(value).strip().casefold():
            return option
    raise AssertionError(f"Unexpected option lookup {group}={value} for {field}")


def test_create_update_fetch_draft_persists_furnishing_status_and_floor(monkeypatch) -> None:
    monkeypatch.setattr("app.services.property_submissions.resolve_property_option", _resolve_option)
    monkeypatch.setattr("app.services.property_submissions.flag_modified", lambda *args, **kwargs: None)

    created = create_submission(
        MagicMock(),
        user_id=uuid4(),
        agency_id=None,
        payload={
            "property_details": {
                "furnishingStatus": 21,
                "floor": 5,
            }
        },
        current_step=4,
        last_completed_step=3,
    )

    assert created.furnishing_status_id == 21
    assert created.floor_id == 5
    created_details = created.payload["property_details"]
    assert created_details["furnishing"] == "furnished"
    assert created_details["furnishing_status"] == "furnished"
    assert created_details["furnishingStatusId"] == 21
    assert created_details["floor"] == 5
    assert created_details["floor_id"] == 5
    assert created_details["floor_number"] == 3
    assert created_details["floorNumber"] == 3

    updated = update_submission(
        MagicMock(),
        created,
        agency_id=None,
        payload={
            "property_details": {
                "furnishing_status_id": 22,
                "floor_id": 8,
            }
        },
        current_step=4,
        last_completed_step=4,
    )

    assert updated.furnishing_status_id == 22
    assert updated.floor_id == 8
    fetched = serialize_submission(updated)
    details = fetched["payload"]["property_details"]
    assert fetched["furnishing_status_id"] == 22
    assert fetched["floor_id"] == 8
    assert details["furnishing_status"] == "semi-furnished"
    assert details["furnishingStatus"] == "semi-furnished"
    assert details["furnishing_status_id"] == 22
    assert details["furnishingStatusId"] == 22
    assert details["floor"] == 6
    assert details["floor_id"] == 8
    assert details["floorId"] == 8
    assert details["floor_number"] == 6
    assert details["floorNumber"] == 6
    assert details["floor_level"] == "Sixth"


def test_serialize_draft_returns_saved_option_ids_from_columns() -> None:
    submission = SimpleNamespace(
        id=uuid4(),
        submitted_by=uuid4(),
        agency_id=None,
        status="draft",
        current_step=4,
        last_completed_step=4,
        step_completion={},
        payload={"property_details": {"furnishing": "furnished", "floor_number": 3}},
        show_location=False,
        reference_number=None,
        furnishing_status_id=21,
        floor_id=5,
        reviewed_by=None,
        reviewed_at=None,
        review_reason=None,
    )

    fetched = serialize_submission(submission)
    details = fetched["payload"]["property_details"]
    assert fetched["furnishing_status_id"] == 21
    assert fetched["floor_id"] == 5
    assert details["furnishing_status_id"] == 21
    assert details["furnishingStatusId"] == 21
    assert details["furnishingStatus"] == "furnished"
    assert details["floor"] == 3
    assert details["floorNumber"] == 3
    assert details["floor_id"] == 5


def test_create_and_update_dtos_accept_furnishing_status_and_floor_aliases() -> None:
    created = PropertySubmissionCreateRequest(
        payload={"property_details": {"furnishingStatus": 21, "floor": 5, "built_up_area": 120}}
    )
    updated = PropertySubmissionUpdateRequest(
        current_step=4,
        last_completed_step=4,
        payload={"property_details": {"furnishingStatusId": 22, "floorId": 8, "guard_name": "Ahmad"}},
    )

    assert created.payload["property_details"]["furnishing_status"] == 21
    assert created.payload["property_details"]["floor"] == 5
    assert created.payload["property_details"]["built_up_area"] == 120
    assert updated.payload["property_details"]["furnishing_status_id"] == 22
    assert updated.payload["property_details"]["floor_id"] == 8
    assert updated.payload["property_details"]["guard_name"] == "Ahmad"


def test_numeric_floor_is_returned_for_draft_restore(monkeypatch) -> None:
    monkeypatch.setattr("app.services.property_submissions.resolve_property_option", _resolve_option)

    created = create_submission(
        MagicMock(),
        user_id=uuid4(),
        agency_id=None,
        payload={"property_details": {"floor": 3, "floorNumber": 3}},
        current_step=4,
        last_completed_step=3,
    )

    details = serialize_submission(created)["payload"]["property_details"]
    assert created.floor_id == 5
    assert details["floor"] == 3
    assert details["floorNumber"] == 3
    assert details["floor_number"] == 3
    assert details["floor_id"] == 5
    assert details["floorLevel"] == "Third"
