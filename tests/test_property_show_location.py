"""Create/update/detail coverage for the property show_location setting."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.property_submissions import (
    apply_show_location_to_payload,
    coerce_bool,
    create_submission,
    resolve_show_location,
    serialize_submission,
    show_location_for_submission,
    update_submission,
)
from app.services import public_properties


def test_coerce_bool_defaults_and_string_values() -> None:
    assert coerce_bool(None) is False
    assert coerce_bool("true") is True
    assert coerce_bool("false") is False
    assert coerce_bool("1") is True
    assert coerce_bool(1) is True
    assert coerce_bool(0) is False


def test_resolve_show_location_defaults_false_when_missing() -> None:
    assert resolve_show_location({}) is False
    assert resolve_show_location({"location": {"city_id": 1}}) is False
    assert resolve_show_location({"location": {"show_location": True}}) is True
    assert resolve_show_location({"show_location": True}) is True


def test_apply_show_location_does_not_create_location_section() -> None:
    payload, value = apply_show_location_to_payload({"basic_information": {"title": "Villa"}})
    assert value is False
    assert "location" not in payload


def test_apply_show_location_writes_toggle_into_location_step() -> None:
    payload, value = apply_show_location_to_payload(
        {"location": {"city_id": 1, "address": "Abdoun", "show_location": "true"}}
    )
    assert value is True
    assert payload["location"]["show_location"] is True
    assert payload["location"]["city_id"] == 1


def test_create_submission_persists_location_step_toggle() -> None:
    db = MagicMock()
    submission = create_submission(
        db,
        user_id=uuid4(),
        agency_id=None,
        payload={"location": {"city_id": 1, "show_location": True}},
        current_step=2,
        last_completed_step=2,
    )
    db.add.assert_called_once_with(submission)
    assert submission.show_location is True
    assert submission.payload["location"]["show_location"] is True


def test_create_submission_defaults_show_location_false() -> None:
    db = MagicMock()
    submission = create_submission(
        db,
        user_id=uuid4(),
        agency_id=None,
        payload={"location": {"city_id": 1}},
        current_step=2,
        last_completed_step=2,
    )
    assert submission.show_location is False
    assert submission.payload["location"]["show_location"] is False


def test_update_submission_saves_location_toggle(monkeypatch) -> None:
    monkeypatch.setattr("app.services.property_submissions.flag_modified", lambda *args, **kwargs: None)
    db = MagicMock()
    submission = SimpleNamespace(
        status="draft",
        payload={"location": {"city_id": 1, "show_location": False}},
        show_location=False,
        agency_id=None,
        current_step=2,
        last_completed_step=2,
        step_completion={},
        property_id=None,
    )
    updated = update_submission(
        db,
        submission,
        agency_id=None,
        payload={"location": {"city_id": 1, "area_id": 2, "show_location": True}},
        current_step=2,
        last_completed_step=2,
    )
    assert updated.show_location is True
    assert updated.payload["location"]["show_location"] is True
    assert updated.payload["location"]["area_id"] == 2


def test_serialize_submission_returns_show_location() -> None:
    submission = SimpleNamespace(
        id=uuid4(),
        submitted_by=uuid4(),
        agency_id=None,
        status="draft",
        current_step=2,
        last_completed_step=2,
        step_completion={"location": True},
        payload={"location": {"city_id": 1, "show_location": True}},
        show_location=True,
        reviewed_by=None,
        reviewed_at=None,
        review_reason=None,
    )
    serialized = serialize_submission(submission)
    assert serialized["show_location"] is True
    assert serialized["payload"]["location"]["show_location"] is True


def test_show_location_for_existing_property_is_false() -> None:
    submission = SimpleNamespace(show_location=False, payload={"location": {"city_id": 1}})
    assert show_location_for_submission(submission) is False


def _detail_listing(*, show_location: bool) -> dict:
    location = {
        "city": "Amman",
        "address": {"en": "Abdoun"},
        "latitude": 31.95,
        "longitude": 35.93,
        "map_embed_url": "https://maps.example/embed",
        "show_location": show_location,
    }
    return {
        "id": 1,
        "listing_type": "sale",
        "propertyType": "Apartment",
        "areaName": "Abdoun",
        "city": "Amman",
        "location": location,
        "location_detail": dict(location),
        "show_location": show_location,
    }


def test_property_detail_keeps_current_location_when_show_location_false(monkeypatch) -> None:
    listing = _detail_listing(show_location=False)
    monkeypatch.setattr(public_properties, "serialize_property_listing", lambda *args, **kwargs: listing)
    monkeypatch.setattr(public_properties, "serialize_property_detail_workflow", lambda *args, **kwargs: {})
    monkeypatch.setattr(public_properties, "_agency_for_submission", lambda *args, **kwargs: None)
    monkeypatch.setattr(public_properties, "_load_property_media", lambda *args, **kwargs: [])
    monkeypatch.setattr(public_properties, "_media_for_details", lambda *args, **kwargs: {})
    monkeypatch.setattr(public_properties, "_feature_ids", lambda *args, **kwargs: [])
    monkeypatch.setattr(public_properties, "_feature_list", lambda *args, **kwargs: [])

    submission = SimpleNamespace(
        payload={},
        property_id=uuid4(),
        id=uuid4(),
        created_at=None,
        updated_at=None,
        reviewed_at=None,
        show_location=False,
    )
    anonymous = public_properties.serialize_property_detail(
        MagicMock(),
        submission,
        include_private_fields=False,
    )
    authenticated = public_properties.serialize_property_detail(
        MagicMock(),
        submission,
        actor_roles=("agent",),
        include_private_fields=True,
    )
    assert anonymous["show_location"] is False
    assert authenticated["show_location"] is False
    assert anonymous["location"]["city"] == "Amman"
    assert authenticated["location"]["city"] == "Amman"
    assert anonymous["latitude"] == 31.95
    assert authenticated["location"]["map_embed_url"] == "https://maps.example/embed"


def test_property_detail_exposes_location_to_all_roles_when_enabled(monkeypatch) -> None:
    listing = _detail_listing(show_location=True)
    monkeypatch.setattr(public_properties, "serialize_property_listing", lambda *args, **kwargs: listing)
    monkeypatch.setattr(public_properties, "serialize_property_detail_workflow", lambda *args, **kwargs: {})
    monkeypatch.setattr(public_properties, "_agency_for_submission", lambda *args, **kwargs: None)
    monkeypatch.setattr(public_properties, "_load_property_media", lambda *args, **kwargs: [])
    monkeypatch.setattr(public_properties, "_media_for_details", lambda *args, **kwargs: {})
    monkeypatch.setattr(public_properties, "_feature_ids", lambda *args, **kwargs: [])
    monkeypatch.setattr(public_properties, "_feature_list", lambda *args, **kwargs: [])

    submission = SimpleNamespace(
        payload={},
        property_id=uuid4(),
        id=uuid4(),
        created_at=None,
        updated_at=None,
        reviewed_at=None,
        show_location=True,
    )
    for include_private, roles in ((False, ()), (True, ("owner",)), (True, ("agent",)), (True, ("admin",))):
        detail = public_properties.serialize_property_detail(
            MagicMock(),
            submission,
            actor_roles=roles,
            include_private_fields=include_private,
        )
        assert detail["show_location"] is True
        assert detail["location"]["show_location"] is True
        assert detail["location_detail"]["latitude"] == 31.95
        assert detail["longitude"] == 35.93
