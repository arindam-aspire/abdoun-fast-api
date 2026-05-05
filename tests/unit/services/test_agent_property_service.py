"""Unit tests for AgentPropertyService."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.agent_property_service import AgentPropertyService


def _user():
    u = MagicMock()
    u.id = uuid.uuid4()
    return u


def _property_row(pid: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=pid,
        property_hash=123456,
        title="Villa Test",
        listing_purpose="sale",
        price=Decimal("500000"),
        currency="JOD",
        reference_number="REF-1",
        created_at=datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 2, 12, 0, 0),
        type=SimpleNamespace(name="Villa", slug="villa"),
        category=SimpleNamespace(name="Residential", slug="residential"),
        property_status=SimpleNamespace(name="Active", slug="active"),
    )


def _submission(pid: uuid.UUID, uid: uuid.UUID, status: str = "submitted") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        property_id=pid,
        submitted_by=uid,
        status=status,
        submitted_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
        reviewed_at=None,
        review_reason=None,
        payload={},
        current_step=8,
        last_completed_step=8,
        updated_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )


def test_list_my_properties_maps_rows() -> None:
    prop_repo = MagicMock()
    sub_repo = MagicMock()
    pid = uuid.uuid4()
    user = _user()
    prop_repo.list_properties_for_agent.return_value = ([_property_row(pid)], 1)
    sub_repo.list_submissions_linked_to_properties.return_value = {}
    sub_repo.list_draft_submissions_without_property.return_value = ([], 0)
    service = AgentPropertyService(property_repository=prop_repo, submission_repository=sub_repo)

    out = service.list_my_properties(user=user, page=1, page_size=200)

    assert out.total == 1
    assert out.page == 1
    assert out.pageSize == 200
    assert len(out.items) == 1
    row = out.items[0]
    assert row.property_id == pid
    assert row.title == "Villa Test"
    assert row.status_slug == "active"
    assert row.type_name == "Villa"
    assert row.price == Decimal("500000")
    assert row.submission_id is None
    assert out.draft_submissions is None


def test_list_my_properties_includes_submission_moderation() -> None:
    prop_repo = MagicMock()
    sub_repo = MagicMock()
    pid = uuid.uuid4()
    user = _user()
    prop_repo.list_properties_for_agent.return_value = ([_property_row(pid)], 1)
    sub = _submission(pid, user.id, status="submitted")
    sub_repo.list_submissions_linked_to_properties.return_value = {pid: sub}
    sub_repo.list_draft_submissions_without_property.return_value = ([], 0)
    service = AgentPropertyService(property_repository=prop_repo, submission_repository=sub_repo)

    out = service.list_my_properties(user=user, page=1, page_size=10)
    row = out.items[0]
    assert row.submission_id == sub.id
    assert row.submission_status == "submitted"
    assert row.submission_submitted_at == sub.submitted_at
    assert row.submission_workflow_label == "pending_admin_approval"
    assert row.can_edit_submission is False
    assert row.can_delete_submission is False


def test_list_my_properties_includes_draft_submissions() -> None:
    prop_repo = MagicMock()
    sub_repo = MagicMock()
    user = _user()
    prop_repo.list_properties_for_agent.return_value = ([], 0)
    sub_repo.list_submissions_linked_to_properties.return_value = {}
    draft = SimpleNamespace(
        id=uuid.uuid4(),
        status="draft",
        current_step=1,
        last_completed_step=0,
        payload={"basic_information": {"title": "WIP Title"}},
        updated_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    sub_repo.list_draft_submissions_without_property.return_value = ([draft], 4)

    service = AgentPropertyService(property_repository=prop_repo, submission_repository=sub_repo)
    out = service.list_my_properties(user=user, page=1, page_size=10)

    assert out.items == []
    assert out.draft_submissions_total is None
    assert out.draft_submissions is None

    out_with_drafts = service.list_my_properties(user=user, page=1, page_size=10, include_drafts=True)
    assert out_with_drafts.draft_submissions_total == 4
    assert len(out_with_drafts.draft_submissions) == 1
    assert out_with_drafts.draft_submissions[0].submission_id == draft.id
    assert out_with_drafts.draft_submissions[0].title == "WIP Title"
    assert out_with_drafts.draft_submissions[0].can_edit is True
    assert out_with_drafts.draft_submissions[0].can_delete is True


def test_list_my_draft_submissions_separate_api_shape() -> None:
    prop_repo = MagicMock()
    sub_repo = MagicMock()
    user = _user()
    prop_repo.list_properties_for_agent.return_value = ([], 0)
    sub_repo.list_submissions_linked_to_properties.return_value = {}
    draft1 = SimpleNamespace(
        id=uuid.uuid4(),
        status="draft",
        current_step=2,
        last_completed_step=1,
        payload={"basic_information": {"title": "Draft 1"}},
        updated_at=datetime(2026, 2, 2, tzinfo=timezone.utc),
    )
    draft2 = SimpleNamespace(
        id=uuid.uuid4(),
        status="in_progress",
        current_step=3,
        last_completed_step=2,
        payload={"basic_information": {"title": "Draft 2"}},
        updated_at=datetime(2026, 2, 3, tzinfo=timezone.utc),
    )
    sub_repo.list_draft_submissions_without_property.return_value = ([draft2, draft1], 2)
    service = AgentPropertyService(property_repository=prop_repo, submission_repository=sub_repo)

    out = service.list_my_draft_submissions(user=user, page=1, page_size=10)
    assert out.total == 2
    assert len(out.items) == 2
    assert out.items[0].title == "Draft 2"


def test_list_my_properties_rejected_allows_edit_delete() -> None:
    prop_repo = MagicMock()
    sub_repo = MagicMock()
    pid = uuid.uuid4()
    user = _user()
    prop_repo.list_properties_for_agent.return_value = ([_property_row(pid)], 1)
    sub = _submission(pid, user.id, status="rejected")
    sub.review_reason = "Too vague"
    sub_repo.list_submissions_linked_to_properties.return_value = {pid: sub}
    sub_repo.list_draft_submissions_without_property.return_value = ([], 0)
    service = AgentPropertyService(property_repository=prop_repo, submission_repository=sub_repo)

    row = service.list_my_properties(user=user, page=1, page_size=10).items[0]
    assert row.submission_workflow_label == "rejected"
    assert row.can_edit_submission is True
    assert row.can_delete_submission is True


def test_list_my_properties_approved_maps_workflow_to_verified() -> None:
    prop_repo = MagicMock()
    sub_repo = MagicMock()
    pid = uuid.uuid4()
    user = _user()
    prop_repo.list_properties_for_agent.return_value = ([_property_row(pid)], 1)
    sub = _submission(pid, user.id, status="approved")
    sub_repo.list_submissions_linked_to_properties.return_value = {pid: sub}
    sub_repo.list_draft_submissions_without_property.return_value = ([], 0)
    service = AgentPropertyService(property_repository=prop_repo, submission_repository=sub_repo)
    row = service.list_my_properties(user=user, page=1, page_size=10).items[0]
    assert row.submission_workflow_label == "verified"
    assert row.can_edit_submission is False
    assert row.can_delete_submission is False


def test_list_my_properties_empty() -> None:
    prop_repo = MagicMock()
    sub_repo = MagicMock()
    prop_repo.list_properties_for_agent.return_value = ([], 0)
    sub_repo.list_submissions_linked_to_properties.return_value = {}
    sub_repo.list_draft_submissions_without_property.return_value = ([], 0)
    service = AgentPropertyService(property_repository=prop_repo, submission_repository=sub_repo)
    out = service.list_my_properties(user=_user(), page=3, page_size=10)
    assert out.items == []
    assert out.total == 0
    assert out.page == 3
