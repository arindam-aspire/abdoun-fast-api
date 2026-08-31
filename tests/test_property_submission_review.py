"""Property submission review authorization and transitions."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.property_submissions import (
    ACTIVE_STATUS,
    REJECTED_STATUS,
    assert_can_review_submission,
    review_submission,
    serialize_property_detail_workflow,
)


def _submission(*, agency_id=None, status: str = "submitted", assigned_agent_id=None):
    owner_id = uuid4()
    return SimpleNamespace(
        id=uuid4(),
        submitted_by=owner_id,
        agency_id=agency_id,
        status=status,
        property_id=None,
        payload={
            "_workflow": {
                "workflow_stage": status,
                "submission_origin": "owner",
                "assigned_agent_id": str(assigned_agent_id) if assigned_agent_id else None,
            }
        },
        review_reason=None,
        reviewed_by=None,
        reviewed_at=None,
    )


@pytest.fixture
def review_side_effects(monkeypatch):
    notification = MagicMock()
    monkeypatch.setattr("app.services.property_submissions.ensure_property_id_and_sync_media", lambda *args: uuid4())
    monkeypatch.setattr("app.services.property_submissions.record_activity", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.property_submissions.create_in_app_notification", notification)
    monkeypatch.setattr("app.services.property_submissions.flag_modified", lambda *args: None)
    return notification


def test_super_admin_directly_approves_agencyless_owner_property(review_side_effects) -> None:
    submission = _submission()
    owner_id = submission.submitted_by
    reviewer_id = uuid4()

    review_submission(
        MagicMock(),
        submission,
        actor_id=reviewer_id,
        actor_roles=("super_admin",),
        actor_agency_id=None,
        action="approve",
    )

    assert submission.status == ACTIVE_STATUS
    assert submission.submitted_by == owner_id
    assert submission.reviewed_by == reviewer_id
    assert submission.reviewed_at is not None
    assert submission.review_reason is None
    assert submission.payload["_workflow"]["workflow_stage"] == ACTIVE_STATUS
    assert review_side_effects.call_args.kwargs["recipient_user_id"] == owner_id


def test_super_admin_directly_rejects_agencyless_owner_property(review_side_effects) -> None:
    submission = _submission()
    reviewer_id = uuid4()

    review_submission(
        MagicMock(),
        submission,
        actor_id=reviewer_id,
        actor_roles=("super_admin",),
        actor_agency_id=None,
        action="reject",
        reason="Incomplete ownership documents",
    )

    assert submission.status == REJECTED_STATUS
    assert submission.review_reason == "Incomplete ownership documents"
    assert submission.reviewed_by == reviewer_id
    assert submission.payload["_workflow"]["workflow_stage"] == REJECTED_STATUS


def test_agencyless_direct_review_requires_super_admin() -> None:
    submission = _submission()

    with pytest.raises(HTTPException) as exc_info:
        assert_can_review_submission(
            MagicMock(),
            submission,
            roles=("admin",),
            agency_id=None,
        )

    assert exc_info.value.status_code == 403


def test_super_admin_cannot_review_agency_assigned_property() -> None:
    submission = _submission(agency_id=uuid4(), status="pending-approval", assigned_agent_id=uuid4())

    with pytest.raises(HTTPException) as exc_info:
        assert_can_review_submission(
            MagicMock(),
            submission,
            roles=("super_admin",),
            agency_id=None,
        )

    assert exc_info.value.status_code == 403


def test_agency_admin_approval_flow_is_unchanged(review_side_effects) -> None:
    agency_id = uuid4()
    submission = _submission(agency_id=agency_id, status="pending-approval", assigned_agent_id=uuid4())

    review_submission(
        MagicMock(),
        submission,
        actor_id=uuid4(),
        actor_roles=("admin",),
        actor_agency_id=agency_id,
        action="approve",
    )

    assert submission.status == ACTIVE_STATUS


def test_super_admin_actions_are_exposed_only_for_agencyless_submission() -> None:
    actor_id = uuid4()
    agencyless = _submission()
    assigned = _submission(agency_id=uuid4())

    agencyless_workflow = serialize_property_detail_workflow(
        MagicMock(),
        agencyless,
        actor_user_id=actor_id,
        actor_roles=("super_admin",),
    )
    assigned_workflow = serialize_property_detail_workflow(
        MagicMock(),
        assigned,
        actor_user_id=actor_id,
        actor_roles=("super_admin",),
    )

    assert [action["id"] for action in agencyless_workflow["workflow_actions"]] == ["approve", "reject"]
    assert assigned_workflow["workflow_actions"] == []
