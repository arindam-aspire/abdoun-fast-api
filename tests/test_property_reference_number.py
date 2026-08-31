"""Server-generated property reference_number coverage."""

from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.models.live_schema import PropertyCategory, PropertyType
from app.services.property_submissions import (
    assign_reference_number,
    create_submission,
    generate_reference_number,
    reference_number_prefix,
    serialize_submission,
    stored_reference_number,
    update_submission,
    write_payload_reference_number,
)

REFERENCE_NUMBER_PATTERN = re.compile(
    r"^[A-Z]{2}-[a-z0-9]{8}-[a-z0-9]{9}-[a-z0-9]{6}-[a-z0-9]{6}$"
)


class _Taxonomy:
    def __init__(self, name: str, slug: str) -> None:
        self.name = name
        self.slug = slug


def _db_with_taxonomy(category: str = "Residential", property_type: str = "Apartments") -> MagicMock:
    db = MagicMock()

    def get(model, ident):
        if model is PropertyCategory:
            return _Taxonomy(category, category.lower())
        if model is PropertyType:
            return _Taxonomy(property_type, property_type.lower())
        return None

    db.get.side_effect = get
    db.execute.return_value.first.return_value = None
    return db


def test_generate_reference_number_matches_unique_segment_format() -> None:
    value = generate_reference_number("RA")
    assert REFERENCE_NUMBER_PATTERN.match(value)
    assert value.startswith("RA-")


def test_reference_prefix_residential_apartment() -> None:
    db = _db_with_taxonomy("Residential", "Apartments")
    payload = {"basic_information": {"category_id": 1, "type_id": 2}}
    assert reference_number_prefix(db, payload) == "RA"


def test_client_provided_reference_number_is_ignored_on_create() -> None:
    db = _db_with_taxonomy()
    submission = create_submission(
        db,
        user_id=uuid4(),
        agency_id=None,
        payload={
            "basic_information": {"category_id": 1, "type_id": 2},
            "property_details": {"bedrooms": 3, "reference_number": "CLIENT-REF"},
        },
        current_step=3,
        last_completed_step=3,
    )
    assert submission.reference_number != "CLIENT-REF"
    assert REFERENCE_NUMBER_PATTERN.match(submission.reference_number)
    assert submission.payload["property_details"]["reference_number"] == submission.reference_number
    assert submission.payload["property_details"]["bedrooms"] == 3


def test_create_does_not_invent_property_details_section() -> None:
    db = _db_with_taxonomy()
    submission = create_submission(
        db,
        user_id=uuid4(),
        agency_id=None,
        payload={"basic_information": {"category_id": 1, "type_id": 2}},
        current_step=1,
        last_completed_step=1,
    )
    assert REFERENCE_NUMBER_PATTERN.match(submission.reference_number)
    assert "property_details" not in submission.payload


def test_update_preserves_existing_reference_and_ignores_client(monkeypatch) -> None:
    monkeypatch.setattr("app.services.property_submissions.flag_modified", lambda *args, **kwargs: None)
    db = _db_with_taxonomy()
    existing = "RA-q3i84ru8-q3i4i7ury-qi34yr-hhhhvg"
    submission = SimpleNamespace(
        id=uuid4(),
        status="draft",
        payload={"basic_information": {"category_id": 1, "type_id": 2}, "property_details": {"reference_number": existing}},
        show_location=False,
        reference_number=existing,
        agency_id=None,
        current_step=3,
        last_completed_step=3,
        step_completion={},
        property_id=None,
    )
    updated = update_submission(
        db,
        submission,
        agency_id=None,
        payload={
            "basic_information": {"category_id": 1, "type_id": 2},
            "property_details": {"bedrooms": 4, "reference_number": "HACKED"},
        },
        current_step=3,
        last_completed_step=3,
    )
    assert updated.reference_number == existing
    assert updated.payload["property_details"]["reference_number"] == existing
    assert updated.payload["property_details"]["bedrooms"] == 4


def test_update_generates_reference_when_missing_and_taxonomy_present(monkeypatch) -> None:
    monkeypatch.setattr("app.services.property_submissions.flag_modified", lambda *args, **kwargs: None)
    db = _db_with_taxonomy()
    submission = SimpleNamespace(
        id=uuid4(),
        status="draft",
        payload={"basic_information": {"category_id": 1, "type_id": 2}},
        show_location=False,
        reference_number=None,
        agency_id=None,
        current_step=1,
        last_completed_step=1,
        step_completion={},
        property_id=None,
    )
    updated = update_submission(
        db,
        submission,
        agency_id=None,
        payload={
            "basic_information": {"category_id": 1, "type_id": 2},
            "property_details": {"bathrooms": 2, "reference_number": "NOPE"},
        },
        current_step=3,
        last_completed_step=3,
    )
    assert updated.reference_number != "NOPE"
    assert REFERENCE_NUMBER_PATTERN.match(updated.reference_number)
    assert updated.payload["property_details"]["reference_number"] == updated.reference_number


def test_assign_strips_client_value_until_taxonomy_exists() -> None:
    db = MagicMock()
    db.get.return_value = None
    payload, value = assign_reference_number(
        db,
        {"property_details": {"reference_number": "CLIENT-REF", "bedrooms": 1}},
    )
    assert value is None
    assert "reference_number" not in payload["property_details"]
    assert payload["property_details"]["bedrooms"] == 1


def test_write_payload_reference_number_does_not_create_details() -> None:
    payload = write_payload_reference_number({"basic_information": {"title": "Villa"}}, "RA-abc")
    assert "property_details" not in payload


def test_serialize_submission_returns_generated_reference() -> None:
    reference = "RA-q3i84ru8-q3i4i7ury-qi34yr-hhhhvg"
    submission = SimpleNamespace(
        id=uuid4(),
        submitted_by=uuid4(),
        agency_id=None,
        status="draft",
        current_step=3,
        last_completed_step=3,
        step_completion={"property_details": True},
        payload={"property_details": {"bedrooms": 2}},
        show_location=False,
        reference_number=reference,
        reviewed_by=None,
        reviewed_at=None,
        review_reason=None,
    )
    serialized = serialize_submission(submission)
    assert serialized["reference_number"] == reference
    assert serialized["payload"]["property_details"]["reference_number"] == reference


def test_stored_reference_number_prefers_column_over_payload() -> None:
    submission = SimpleNamespace(
        reference_number="RA-from-column",
        payload={"property_details": {"reference_number": "legacy"}},
    )
    assert stored_reference_number(submission) == "RA-from-column"
