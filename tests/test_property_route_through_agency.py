"""Create Property agency-routing coverage."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.schemas.property_submissions import (
    PropertySubmissionCreateRequest,
    PropertySubmissionDirectSubmitRequest,
    PropertySubmissionUpdateRequest,
)
from app.services import public_properties
from app.services.property_submissions import (
    ACTIVE_STATUS,
    assert_can_review_submission,
    create_submission,
    review_submission,
    serialize_draft_list_item,
    serialize_submission,
    submit_submission,
    update_submission,
)


def _payload() -> dict:
    return {"media_documents": {"images": [{"url": "https://example.com/property.jpg"}]}}


def test_create_and_direct_submit_requests_default_to_no_agency_routing() -> None:
    assert PropertySubmissionCreateRequest(payload={}).route_through_agency is False
    assert PropertySubmissionDirectSubmitRequest(payload={}, confirm_submit=True).route_through_agency is False


def test_requests_accept_verify_through_agency_alias() -> None:
    agency_id = uuid4()
    created = PropertySubmissionCreateRequest.model_validate(
        {"verify_through_agency": True, "agency_id": str(agency_id), "payload": {}}
    )
    submitted = PropertySubmissionDirectSubmitRequest.model_validate(
        {"verify_through_agency": False, "agency_id": None, "confirm_submit": True, "payload": {}}
    )
    updated = PropertySubmissionUpdateRequest.model_validate(
        {"verify_through_agency": True, "agency_id": str(agency_id), "current_step": 1, "last_completed_step": 0, "payload": {}}
    )

    assert created.route_through_agency is True
    assert created.agency_id == agency_id
    assert submitted.route_through_agency is False
    assert submitted.agency_id is None
    assert updated.route_through_agency is True
    assert updated.agency_id == agency_id


def test_update_request_can_omit_agency_routing() -> None:
    request = PropertySubmissionUpdateRequest(current_step=1, last_completed_step=0, payload={})

    assert request.route_through_agency is None


def test_create_draft_ignores_agency_when_routing_is_false() -> None:
    db = MagicMock()

    submission = create_submission(
        db,
        user_id=uuid4(),
        agency_id=uuid4(),
        route_through_agency=False,
        payload={},
        current_step=1,
        last_completed_step=0,
    )

    assert submission.route_through_agency is False
    assert submission.agency_id is None
    db.get.assert_not_called()


def test_create_draft_requires_active_agency_when_routing_is_true() -> None:
    db = MagicMock()
    db.get.return_value = SimpleNamespace(is_active=False)

    with pytest.raises(HTTPException) as exc_info:
        create_submission(
            db,
            user_id=uuid4(),
            agency_id=uuid4(),
            route_through_agency=True,
            payload={},
            current_step=1,
            last_completed_step=0,
        )

    assert exc_info.value.status_code == 400


def test_create_draft_requires_agency_id_when_routing_is_true() -> None:
    with pytest.raises(HTTPException) as exc_info:
        create_submission(
            MagicMock(),
            user_id=uuid4(),
            agency_id=None,
            route_through_agency=True,
            payload={},
            current_step=1,
            last_completed_step=0,
        )

    assert exc_info.value.status_code == 400


def test_create_draft_persists_valid_agency_routing() -> None:
    db = MagicMock()
    db.get.return_value = SimpleNamespace(is_active=True)
    agency_id = uuid4()

    submission = create_submission(
        db,
        user_id=uuid4(),
        agency_id=agency_id,
        route_through_agency=True,
        payload={},
        current_step=1,
        last_completed_step=0,
    )

    assert submission.route_through_agency is True
    assert submission.agency_id == agency_id


def test_create_draft_applies_owner_agency_authorization(monkeypatch) -> None:
    db = MagicMock()
    db.get.return_value = SimpleNamespace(is_active=True)
    agency_id = uuid4()
    owner_id = uuid4()
    authorize = MagicMock()
    monkeypatch.setattr("app.services.property_submissions.assert_owner_agency_rule", authorize)

    create_submission(
        db,
        user_id=owner_id,
        roles=("owner",),
        agency_id=agency_id,
        route_through_agency=True,
        payload={},
        current_step=1,
        last_completed_step=0,
    )

    authorize.assert_called_once_with(db, user_id=owner_id, agency_id=agency_id, roles=("owner",))


def test_update_draft_clears_agency_when_routing_is_disabled(monkeypatch) -> None:
    monkeypatch.setattr("app.services.property_submissions.flag_modified", lambda *args: None)
    submission = SimpleNamespace(
        status="draft",
        submitted_by=uuid4(),
        route_through_agency=True,
        agency_id=uuid4(),
        payload={},
        property_id=None,
        step_completion={},
    )

    update_submission(
        MagicMock(),
        submission,
        agency_id=None,
        route_through_agency=False,
        payload={},
        current_step=1,
        last_completed_step=0,
    )

    assert submission.route_through_agency is False
    assert submission.agency_id is None


def test_submit_without_agency_routing_allows_null_agency(monkeypatch) -> None:
    monkeypatch.setattr("app.services.property_submissions._next_status_on_submit", lambda *args, **kwargs: "submitted")
    monkeypatch.setattr("app.services.property_submissions.ensure_property_id_and_sync_media", lambda *args: uuid4())
    monkeypatch.setattr("app.services.property_submissions.notify_agency_admins_for_submission", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.property_submissions.flag_modified", lambda *args: None)
    submission = SimpleNamespace(
        id=uuid4(),
        submitted_by=uuid4(),
        route_through_agency=False,
        agency_id=uuid4(),
        property_id=None,
        status="draft",
        submitted_at=None,
        step_completion={},
        payload=_payload(),
    )

    submit_submission(MagicMock(), submission, user_id=submission.submitted_by, roles=())

    assert submission.agency_id is None
    assert submission.status == "submitted"


def test_draft_responses_return_routing_fields() -> None:
    agency_id = uuid4()
    submission = SimpleNamespace(
        id=uuid4(),
        submitted_by=uuid4(),
        route_through_agency=True,
        agency_id=agency_id,
        status="draft",
        current_step=1,
        last_completed_step=0,
        step_completion={},
        payload={},
        show_location=False,
        reference_number=None,
        reviewed_by=None,
        reviewed_at=None,
        review_reason=None,
        updated_at=None,
    )

    detail = serialize_submission(submission)
    list_item = serialize_draft_list_item(submission)

    assert detail["route_through_agency"] is True
    assert detail["verify_through_agency"] is True
    assert detail["agency_id"] == str(agency_id)
    assert list_item["route_through_agency"] is True
    assert list_item["verify_through_agency"] is True
    assert list_item["agency_id"] == str(agency_id)


def test_property_response_ignores_user_agency_when_routing_is_false() -> None:
    db = MagicMock()
    submission = SimpleNamespace(route_through_agency=False, agency_id=None)
    user = SimpleNamespace(agency_id=uuid4())

    assert public_properties._agency_for_submission(db, submission, user) is None
    db.get.assert_not_called()


def _patch_submit(monkeypatch) -> MagicMock:
    mapping = MagicMock()
    monkeypatch.setattr("app.services.property_submissions.ensure_property_id_and_sync_media", lambda *args: uuid4())
    monkeypatch.setattr("app.services.property_submissions.notify_agency_admins_for_submission", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.property_submissions.record_owner_agency_mapping_for_submission", mapping)
    monkeypatch.setattr("app.services.property_submissions.flag_modified", lambda *args: None)
    return mapping


def _patch_review(monkeypatch) -> None:
    monkeypatch.setattr("app.services.property_submissions.ensure_property_id_and_sync_media", lambda *args: uuid4())
    monkeypatch.setattr("app.services.property_submissions.record_activity", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.property_submissions.create_in_app_notification", MagicMock())
    monkeypatch.setattr("app.services.property_submissions.flag_modified", lambda *args: None)


def test_owner_submit_without_agency_uses_super_admin_workflow(monkeypatch) -> None:
    _patch_submit(monkeypatch)
    _patch_review(monkeypatch)
    owner_id = uuid4()

    submission = create_submission(
        MagicMock(),
        user_id=owner_id,
        roles=("owner",),
        agency_id=None,
        route_through_agency=False,
        payload=_payload(),
        current_step=8,
        last_completed_step=8,
    )
    submit_submission(MagicMock(), submission, user_id=owner_id, roles=("owner",))

    assert submission.agency_id is None
    assert submission.route_through_agency is False
    assert submission.status == "submitted"
    assert submission.payload["_workflow"]["current_actor"] == "super_admin"
    assert submission.payload["_workflow"]["submission_origin"] == "owner"

    assert_can_review_submission(MagicMock(), submission, roles=("super_admin",), agency_id=None)
    with pytest.raises(HTTPException) as exc_info:
        assert_can_review_submission(MagicMock(), submission, roles=("admin",), agency_id=uuid4())
    assert exc_info.value.status_code == 403

    reviewer_id = uuid4()
    review_submission(
        MagicMock(),
        submission,
        actor_id=reviewer_id,
        actor_roles=("super_admin",),
        actor_agency_id=None,
        action="reject",
        reason="Please update the ownership documents",
    )
    assert submission.status == "rejected"
    assert submission.review_reason == "Please update the ownership documents"
    assert submission.reviewed_by == reviewer_id


def test_owner_submit_with_agency_keeps_existing_agency_workflow(monkeypatch) -> None:
    mapping = _patch_submit(monkeypatch)
    monkeypatch.setattr("app.services.property_submissions.assert_owner_agency_rule", lambda *args, **kwargs: None)
    db = MagicMock()
    db.get.return_value = SimpleNamespace(is_active=True)
    agency_id = uuid4()
    owner_id = uuid4()

    submission = create_submission(
        db,
        user_id=owner_id,
        roles=("owner",),
        agency_id=agency_id,
        route_through_agency=True,
        payload=_payload(),
        current_step=8,
        last_completed_step=8,
    )
    submit_submission(db, submission, user_id=owner_id, roles=("owner",))

    assert submission.agency_id == agency_id
    assert submission.route_through_agency is True
    assert submission.status == "submitted"
    assert submission.payload["_workflow"]["current_actor"] == "agency_admin"
    mapping.assert_called_once()

    with pytest.raises(HTTPException) as exc_info:
        assert_can_review_submission(db, submission, roles=("super_admin",), agency_id=None)
    assert exc_info.value.status_code == 403

    assert_can_review_submission(db, submission, roles=("admin",), agency_id=agency_id)


def test_agency_admin_create_keeps_agency_when_verify_flag_is_false() -> None:
    db = MagicMock()
    db.get.return_value = SimpleNamespace(is_active=True)
    agency_id = uuid4()

    submission = create_submission(
        db,
        user_id=uuid4(),
        roles=("admin",),
        agency_id=agency_id,
        route_through_agency=False,
        payload={},
        current_step=1,
        last_completed_step=0,
    )

    assert submission.agency_id == agency_id
    assert submission.route_through_agency is True


def test_update_does_not_clear_agency_for_admin_when_flag_is_false(monkeypatch) -> None:
    monkeypatch.setattr("app.services.property_submissions.flag_modified", lambda *args: None)
    db = MagicMock()
    db.get.return_value = SimpleNamespace(is_active=True)
    agency_id = uuid4()
    submission = SimpleNamespace(
        status="draft",
        submitted_by=uuid4(),
        route_through_agency=True,
        agency_id=agency_id,
        payload={},
        property_id=None,
        step_completion={},
    )

    update_submission(
        db,
        submission,
        agency_id=agency_id,
        route_through_agency=False,
        payload={},
        current_step=1,
        last_completed_step=0,
        roles=("admin",),
    )

    assert submission.agency_id == agency_id
    assert submission.route_through_agency is True
