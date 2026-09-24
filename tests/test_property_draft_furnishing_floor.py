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
        ("land_type", 401): SimpleNamespace(
            id=401, slug="building-offices", name="بناء/مكاتب", numeric_value=None
        ),
        ("land_type", 402): SimpleNamespace(
            id=402, slug="building-warehouses", name="بناء/مخازن", numeric_value=None
        ),
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
            "basic_information": {"category_slug": "residential"},
            "property_details": {
                "furnishingStatus": 21,
                "floor": 5,
                "landTypeId": 401,
            }
        },
        current_step=4,
        last_completed_step=3,
    )

    assert created.furnishing_status_id == 21
    assert created.floor_id == 5
    assert created.land_type_id == 401
    created_details = created.payload["property_details"]
    assert created_details["furnishing"] == "furnished"
    assert created_details["furnishing_status"] == "furnished"
    assert created_details["furnishingStatusId"] == 21
    assert created_details["floor"] == 5
    assert created_details["floor_id"] == 5
    assert created_details["floor_number"] == "3"
    assert created_details["floorNumber"] == "3"
    assert created_details["land_type"] == "building-offices"
    assert created_details["land_type_id"] == 401
    assert created_details["land_type_name"] == "بناء/مكاتب"

    updated = update_submission(
        MagicMock(),
        created,
        agency_id=None,
        payload={
            "basic_information": {"category_slug": "residential"},
            "property_details": {
                "furnishing_status_id": 22,
                "floor_id": 8,
                "land_type_id": 402,
            }
        },
        current_step=4,
        last_completed_step=4,
    )

    assert updated.furnishing_status_id == 22
    assert updated.floor_id == 8
    assert updated.land_type_id == 402
    fetched = serialize_submission(updated)
    details = fetched["payload"]["property_details"]
    assert fetched["furnishing_status_id"] == 22
    assert fetched["floor_id"] == 8
    assert fetched["land_type_id"] == 402
    assert details["furnishing_status"] == "semi-furnished"
    assert details["furnishingStatus"] == "semi-furnished"
    assert details["furnishing_status_id"] == 22
    assert details["furnishingStatusId"] == 22
    assert details["floor"] == 6
    assert details["floor_id"] == 8
    assert details["floorId"] == 8
    assert details["floor_number"] == "6"
    assert details["floorNumber"] == "6"
    assert details["floor_level"] == "Sixth"
    assert details["land_type"] == "building-warehouses"
    assert details["land_type_id"] == 402
    assert details["landTypeId"] == 402


def test_serialize_draft_returns_saved_option_ids_from_columns() -> None:
    submission = SimpleNamespace(
        id=uuid4(),
        submitted_by=uuid4(),
        agency_id=None,
        status="draft",
        current_step=4,
        last_completed_step=4,
        step_completion={},
        payload={
            "property_details": {
                "furnishing": "furnished",
                "floor_number": 3,
                "land_type": "building-offices",
            }
        },
        show_location=False,
        reference_number=None,
        furnishing_status_id=21,
        floor_id=5,
        land_type_id=401,
        reviewed_by=None,
        reviewed_at=None,
        review_reason=None,
    )

    fetched = serialize_submission(submission)
    details = fetched["payload"]["property_details"]
    assert fetched["furnishing_status_id"] == 21
    assert fetched["floor_id"] == 5
    assert fetched["land_type_id"] == 401
    assert details["furnishing_status_id"] == 21
    assert details["furnishingStatusId"] == 21
    assert details["furnishingStatus"] == "furnished"
    assert details["floor"] == 3
    assert details["floorNumber"] == 3
    assert details["floor_id"] == 5
    assert details["land_type_id"] == 401
    assert details["landTypeId"] == 401
    assert details["landType"] == "building-offices"


def test_create_and_update_dtos_accept_furnishing_status_and_floor_aliases() -> None:
    created = PropertySubmissionCreateRequest(
        payload={
            "property_details": {
                "furnishingStatus": 21,
                "floor": 5,
                "landTypeId": 401,
                "built_up_area": 120,
                "parkingSpace": 2,
            }
        }
    )
    updated = PropertySubmissionUpdateRequest(
        current_step=4,
        last_completed_step=4,
        payload={
            "property_details": {
                "furnishingStatusId": 22,
                "floorId": 8,
                "landType": "بناء/مخازن",
                "guard_name": "Ahmad",
            }
        },
    )

    assert created.payload["property_details"]["furnishing_status"] == 21
    assert created.payload["property_details"]["floor"] == 5
    assert created.payload["property_details"]["land_type_id"] == 401
    assert created.payload["property_details"]["built_up_area"] == 120
    assert created.payload["property_details"]["parking_spaces"] == 2
    assert updated.payload["property_details"]["furnishing_status_id"] == 22
    assert updated.payload["property_details"]["floor_id"] == 8
    assert updated.payload["property_details"]["land_type"] == "بناء/مخازن"
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
    assert details["floorNumber"] == "3"
    assert details["floor_number"] == "3"
    assert details["floor_id"] == 5
    assert details["floorLevel"] == "Third"


def test_draft_persists_and_returns_full_dls_identification_set(monkeypatch) -> None:
    monkeypatch.setattr("app.services.property_submissions.resolve_property_option", _resolve_option)
    monkeypatch.setattr("app.services.property_submissions.flag_modified", lambda *args, **kwargs: None)

    created = create_submission(
        MagicMock(),
        user_id=uuid4(),
        agency_id=None,
        payload={
            "basic_information": {"category_slug": "residential"},
            "location": {
                "gov_code": "1",
                "gov_name": "Capital",
                "dept_code": "11",
                "dept_name": "Dir-A",
                "vill_code": "101",
                "vill_name": "Vill-A",
                "hod_code": "H-9",
                "hod_name": "Hod-A",
                "sect_code": "3",
                "sect_name": "Sect-A",
                "parcel_number": "P-44",
                "plot_number": "88",
                "building": "14",
                "apartment": "12A",
            },
            "property_details": {
                "floor": 5,
                "landTypeId": 401,
            },
        },
        current_step=3,
        last_completed_step=2,
    )

    serialized = serialize_submission(created)
    location = serialized["payload"]["location"]
    details = serialized["payload"]["property_details"]

    assert created.land_type_id == 401
    assert created.floor_id == 5
    assert serialized["land_type_id"] == 401
    assert serialized["floor_id"] == 5

    assert location["gov_code"] == "1"
    assert location["gov_name"] == "Capital"
    assert location["dept_code"] == "11"
    assert location["dept_name"] == "Dir-A"
    assert location["vill_code"] == "101"
    assert location["vill_name"] == "Vill-A"
    assert location["hod_code"] == "H-9"
    assert location["hod_name"] == "Hod-A"
    assert location["sect_code"] == "3"
    assert location["sect_name"] == "Sect-A"
    assert location["parcel_number"] == "P-44"
    assert location["plot_number"] == "88"
    assert location["building_number"] == "14"
    assert location["building"] == "14"
    assert location["apartment_number"] == "12A"

    assert details["land_type_id"] == 401
    assert details["land_type"] == "building-offices"
    assert details["floor_id"] == 5
    assert details["floor_number"] == "3"
    assert details["parcel_number"] == "P-44"
    assert details["plot_number"] == "88"
    assert details["building_number"] == "14"
    assert details["apartment_number"] == "12A"


def test_land_draft_keeps_only_applicable_dls_fields(monkeypatch) -> None:
    monkeypatch.setattr("app.services.property_submissions.resolve_property_option", _resolve_option)

    created = create_submission(
        MagicMock(),
        user_id=uuid4(),
        agency_id=None,
        payload={
            "basic_information": {"category_slug": "land", "category": "land"},
            "location": {
                "gov_code": "1",
                "gov_name": "Capital",
                "dept_code": "11",
                "vill_code": "101",
                "hod_code": "H-1",
                "sect_code": "0",
                "plot_number": "220",
                "parcel_number": "drop-me",
                "building": "Tower-1",
                "apartment": "A-4",
            },
            "property_details": {
                "landTypeId": 401,
                "floor": 5,
            },
        },
        current_step=3,
        last_completed_step=2,
    )

    serialized = serialize_submission(created)
    location = serialized["payload"]["location"]
    details = serialized["payload"]["property_details"]

    assert created.land_type_id is None
    assert created.floor_id is None
    assert serialized["land_type_id"] is None
    assert serialized["floor_id"] is None

    assert location["gov_code"] == "1"
    assert location["dept_code"] == "11"
    assert location["vill_code"] == "101"
    assert location["hod_code"] == "H-1"
    assert location["sect_code"] == "0"
    assert location["plot_number"] == "220"
    assert details["plot_number"] == "220"

    assert "parcel_number" not in location
    assert "building_number" not in location
    assert "building" not in location
    assert "apartment_number" not in location
    assert "land_type" not in details
    assert "land_type_id" not in details
    assert "floor" not in details
    assert "floor_id" not in details
    assert "floor_number" not in details
