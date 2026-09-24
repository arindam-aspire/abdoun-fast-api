"""Server-generated property reference_number coverage."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.models.live_schema import PropertyCategory, PropertyType
from app.services.property_reference_numbers import (
    format_reference_number,
    regenerate_reference_assignments,
)
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
from app.services.property_taxonomy import reference_number_prefix_from_labels


class _Taxonomy:
    def __init__(self, name: str, slug: str) -> None:
        self.name = name
        self.slug = slug


def _db_with_taxonomy(
    category: str = "Residential",
    property_type: str = "Apartments",
    *,
    next_values: list[int] | None = None,
) -> MagicMock:
    db = MagicMock()
    sequence = list(next_values or [1])

    def get(model, ident):
        if model is PropertyCategory:
            return _Taxonomy(category, category.lower())
        if model is PropertyType:
            return _Taxonomy(property_type, property_type.lower().replace(" ", "-"))
        return None

    def execute(stmt, *args, **kwargs):
        result = MagicMock()
        sql = str(stmt)
        if "nextval" in sql:
            result.scalar.return_value = sequence.pop(0) if sequence else 1
            result.first.return_value = None
            return result
        # uniqueness lookup compiled by SQLAlchemy; treat as free unless tests inject taken via payload match
        result.scalar.return_value = None
        result.first.return_value = None
        return result

    db.get.side_effect = get
    db.execute.side_effect = execute
    return db


def _residential_apartment_payload(**details: object) -> dict:
    payload: dict = {"basic_information": {"category_id": 1, "type_id": 2}}
    if details:
        payload["property_details"] = dict(details)
    return payload


def test_generate_reference_number_pads_to_four_digits() -> None:
    assert generate_reference_number(1, "RA") == "RA0001"
    assert generate_reference_number(2, "CO") == "CO0002"
    assert generate_reference_number(1001, "RA") == "RA1001"
    assert generate_reference_number(10026, "CCL") == "CCL10026"
    assert format_reference_number("3", "CO") == "CO0003"


def test_prefix_from_master_data_labels() -> None:
    assert reference_number_prefix_from_labels("Residential", "Apartments") == "RA"
    assert reference_number_prefix_from_labels("Commercial", "Offices") == "CO"
    assert reference_number_prefix_from_labels("Commercial", "Commercial Lands") == "CCL"
    assert reference_number_prefix_from_labels("Land", "Residential Lands") == "LRL"


def test_reference_prefix_residential_apartment() -> None:
    db = _db_with_taxonomy("Residential", "Apartments")
    payload = {"basic_information": {"category_id": 1, "type_id": 2}}
    assert reference_number_prefix(db, payload) == "RA"


def test_reference_prefix_commercial_office_and_commercial_lands() -> None:
    office_db = _db_with_taxonomy("Commercial", "Offices")
    lands_db = _db_with_taxonomy("Commercial", "Commercial Lands")
    payload = {"basic_information": {"category_id": 2, "type_id": 3}}
    assert reference_number_prefix(office_db, payload) == "CO"
    assert reference_number_prefix(lands_db, payload) == "CCL"


def test_reference_prefix_uses_taxonomy_config_when_db_rows_missing() -> None:
    db = MagicMock()
    db.get.return_value = None
    payload = {
        "basic_information": {
            "category_slug": "commercial",
            "type_slug": "commercial-lands",
        }
    }
    assert reference_number_prefix(db, payload) == "CCL"


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
    assert submission.reference_number == "RA0001"
    assert submission.payload["property_details"]["reference_number"] == "RA0001"
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
    assert submission.reference_number == "RA0001"
    assert "property_details" not in submission.payload


def test_draft_without_category_does_not_consume_sequence() -> None:
    db = MagicMock()
    db.get.return_value = None
    payload, value = assign_reference_number(db, {"property_details": {"bedrooms": 1}})
    assert value is None
    assert "reference_number" not in payload["property_details"]
    for call in db.execute.call_args_list:
        assert "nextval" not in str(call.args[0])


def test_update_preserves_existing_reference_and_ignores_client(monkeypatch) -> None:
    monkeypatch.setattr("app.services.property_submissions.flag_modified", lambda *args, **kwargs: None)
    db = _db_with_taxonomy(next_values=[9])
    existing = "RA0001"
    submission = SimpleNamespace(
        id=uuid4(),
        status="draft",
        payload=_residential_apartment_payload(reference_number=existing),
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
            "basic_information": {"category_id": 2, "type_id": 3},
            "property_details": {"bedrooms": 4, "reference_number": "HACKED"},
        },
        current_step=3,
        last_completed_step=3,
    )
    assert updated.reference_number == existing
    assert updated.payload["property_details"]["reference_number"] == existing
    assert updated.payload["property_details"]["bedrooms"] == 4
    for call in db.execute.call_args_list:
        assert "nextval" not in str(call.args[0])


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
    assert updated.reference_number == "RA0001"
    assert updated.payload["property_details"]["reference_number"] == "RA0001"


def test_draft_create_then_save_does_not_consume_another_sequence(monkeypatch) -> None:
    monkeypatch.setattr("app.services.property_submissions.flag_modified", lambda *args, **kwargs: None)
    db = _db_with_taxonomy(next_values=[1, 2])
    submission = create_submission(
        db,
        user_id=uuid4(),
        agency_id=None,
        payload=_residential_apartment_payload(bedrooms=1),
        current_step=3,
        last_completed_step=3,
    )
    assert submission.reference_number == "RA0001"
    updated = update_submission(
        db,
        submission,
        agency_id=None,
        payload=_residential_apartment_payload(bedrooms=2),
        current_step=3,
        last_completed_step=3,
    )
    assert updated.reference_number == "RA0001"
    nextval_calls = [call for call in db.execute.call_args_list if "nextval" in str(call.args[0])]
    assert len(nextval_calls) == 1


def test_assign_strips_client_value_and_generates_prefixed_sequence() -> None:
    db = _db_with_taxonomy("Commercial", "Offices", next_values=[2])
    payload, value = assign_reference_number(
        db,
        {
            "basic_information": {"category_id": 2, "type_id": 3},
            "property_details": {"reference_number": "CLIENT-REF", "bedrooms": 1},
        },
    )
    assert value == "CO0002"
    assert payload["property_details"]["reference_number"] == "CO0002"
    assert payload["property_details"]["bedrooms"] == 1


def test_write_payload_reference_number_does_not_create_details() -> None:
    payload = write_payload_reference_number({"basic_information": {"title": "Villa"}}, "RA0001")
    assert "property_details" not in payload


def test_serialize_submission_returns_generated_reference() -> None:
    reference = "RA0001"
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
        reference_number="RA0001",
        payload={"property_details": {"reference_number": "legacy"}},
    )
    assert stored_reference_number(submission) == "RA0001"


def test_allocate_is_global_sequential_across_categories() -> None:
    residential = _db_with_taxonomy("Residential", "Apartments", next_values=[1])
    commercial = _db_with_taxonomy("Commercial", "Offices", next_values=[2])
    first, first_value = assign_reference_number(
        residential,
        {"basic_information": {"category_id": 1, "type_id": 2}, "property_details": {}},
    )
    second, second_value = assign_reference_number(
        commercial,
        {"basic_information": {"category_id": 2, "type_id": 3}, "property_details": {}},
    )
    assert first_value == "RA0001"
    assert second_value == "CO0002"
    assert first["property_details"]["reference_number"] == "RA0001"
    assert second["property_details"]["reference_number"] == "CO0002"


def test_allocate_retries_when_candidate_already_taken() -> None:
    db = MagicMock()
    db.get.side_effect = lambda model, ident: (
        _Taxonomy("Residential", "residential") if model is PropertyCategory else _Taxonomy("Apartments", "apartments")
    )
    next_values = iter([1, 2])
    uniqueness_checks = iter([True, False])

    def execute(stmt, *args, **kwargs):
        result = MagicMock()
        if "nextval" in str(stmt):
            result.scalar.return_value = next(next_values)
            result.first.return_value = None
            return result
        result.first.return_value = (uuid4(),) if next(uniqueness_checks) else None
        return result

    db.execute.side_effect = execute
    _, value = assign_reference_number(
        db,
        {"basic_information": {"category_id": 1, "type_id": 2}, "property_details": {}},
    )
    assert value == "RA0002"


def test_concurrent_allocation_uses_distinct_sequence_values() -> None:
    lock = threading.Lock()
    counter = 0
    allocated: list[str] = []

    db = MagicMock()
    db.get.side_effect = lambda model, ident: (
        _Taxonomy("Residential", "residential") if model is PropertyCategory else _Taxonomy("Apartments", "apartments")
    )

    def execute(stmt, *args, **kwargs):
        nonlocal counter
        result = MagicMock()
        if "nextval" in str(stmt):
            with lock:
                counter += 1
                result.scalar.return_value = counter
            result.first.return_value = None
            return result
        result.first.return_value = None
        return result

    db.execute.side_effect = execute

    def worker() -> None:
        _, value = assign_reference_number(
            db,
            {"basic_information": {"category_id": 1, "type_id": 2}, "property_details": {}},
        )
        allocated.append(value)

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(allocated) == 12
    assert len(set(allocated)) == 12
    assert allocated[0].startswith("RA")
    numbers = sorted(int(value[2:]) for value in allocated)
    assert numbers == list(range(1, 13))


def test_existing_data_migration_regenerates_in_created_at_order() -> None:
    first_id = uuid4()
    second_id = uuid4()
    third_id = uuid4()
    start = datetime(2026, 1, 1)
    rows = [
        {
            "id": third_id,
            "created_at": start + timedelta(days=2),
            "reference_number": "10003",
            "category_name": "Residential",
            "type_name": "Apartments",
        },
        {
            "id": first_id,
            "created_at": start,
            "reference_number": "10001",
            "category_name": "Residential",
            "type_name": "Apartments",
        },
        {
            "id": second_id,
            "created_at": start + timedelta(days=1),
            "reference_number": "LEGACY-CO",
            "category_name": "Commercial",
            "type_name": "Offices",
        },
    ]
    assignments = regenerate_reference_assignments(rows)
    by_id = {item["id"]: item for item in assignments}
    assert by_id[first_id]["reference_number"] == "RA0001"
    assert by_id[second_id]["reference_number"] == "CO0002"
    assert by_id[third_id]["reference_number"] == "RA0003"
    assert [item["previous_reference_number"] for item in assignments] == ["10001", "LEGACY-CO", "10003"]
    assert regenerate_reference_assignments(rows) == assignments


def test_existing_data_migration_uses_id_as_created_at_tie_breaker() -> None:
    earlier_id = uuid4()
    later_id = uuid4()
    low, high = sorted([earlier_id, later_id], key=str)
    created_at = datetime(2026, 3, 1)
    rows = [
        {
            "id": high,
            "created_at": created_at,
            "reference_number": "B",
            "category_name": "Commercial",
            "type_name": "Offices",
        },
        {
            "id": low,
            "created_at": created_at,
            "reference_number": "A",
            "category_name": "Residential",
            "type_name": "Apartments",
        },
    ]
    assignments = regenerate_reference_assignments(rows)
    assert assignments[0]["id"] == low
    assert assignments[0]["reference_number"] == "RA0001"
    assert assignments[1]["id"] == high
    assert assignments[1]["reference_number"] == "CO0002"
