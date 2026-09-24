"""Draft listing delete authorization and response coverage."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.routes import property_submissions as property_submission_routes
from app.services.property_submissions import (
    assert_can_delete_submission,
    can_delete_submission,
    get_submission_or_404,
    list_submissions,
    serialize_draft_list_item,
    soft_delete_submission,
)


def _draft(submitted_by, *, status: str = "draft", deleted_at=None):
    return SimpleNamespace(
        id=uuid4(),
        submitted_by=submitted_by,
        status=status,
        property_id=None,
        deleted_at=deleted_at,
        deleted_by=None,
        delete_reason=None,
        current_step=3,
        last_completed_step=2,
        payload={"basic_information": {"title": "Draft villa"}},
        updated_at=datetime.now(timezone.utc),
        route_through_agency=False,
        agency_id=None,
    )


def test_creator_can_delete_own_draft() -> None:
    user_id = uuid4()
    submission = _draft(user_id)
    assert can_delete_submission(MagicMock(), submission, user_id=user_id, roles=("owner",), agency_id=None) is True


def test_other_user_cannot_delete_someone_elses_draft() -> None:
    submission = _draft(uuid4())
    assert can_delete_submission(MagicMock(), submission, user_id=uuid4(), roles=("owner",), agency_id=None) is False
    with pytest.raises(HTTPException) as exc_info:
        assert_can_delete_submission(MagicMock(), submission, user_id=uuid4(), roles=("agent",), agency_id=uuid4())
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "FORBIDDEN"


def test_deleted_submission_is_not_found() -> None:
    submission = _draft(uuid4(), deleted_at=datetime.now(timezone.utc))
    db = MagicMock()
    db.get.return_value = submission
    with pytest.raises(HTTPException) as exc_info:
        get_submission_or_404(db, submission.id)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "NOT_FOUND"


def test_delete_route_soft_deletes_and_returns_success_payload(monkeypatch) -> None:
    user_id = uuid4()
    submission = _draft(user_id)
    db = MagicMock()
    context = SimpleNamespace(user_id=user_id, roles=("owner",), agency_id=None)

    monkeypatch.setattr(property_submission_routes, "get_submission_or_404", lambda *_args, **_kwargs: submission)
    monkeypatch.setattr(property_submission_routes, "record_activity", lambda *_args, **_kwargs: None)

    response = property_submission_routes.delete_property_submission(submission.id, context, db)

    assert submission.deleted_at is not None
    assert submission.deleted_by == user_id
    assert db.commit.call_count == 1
    assert response["success"] is True
    assert response["data"] == {"submission_id": str(submission.id), "deleted": True}


def test_delete_route_rejects_unauthorized_user(monkeypatch) -> None:
    submission = _draft(uuid4())
    db = MagicMock()
    context = SimpleNamespace(user_id=uuid4(), roles=("owner",), agency_id=None)
    monkeypatch.setattr(property_submission_routes, "get_submission_or_404", lambda *_args, **_kwargs: submission)

    with pytest.raises(HTTPException) as exc_info:
        property_submission_routes.delete_property_submission(submission.id, context, db)

    assert exc_info.value.status_code == 403
    db.commit.assert_not_called()
    assert submission.deleted_at is None


def test_draft_list_item_can_delete_is_owner_aware() -> None:
    owner_id = uuid4()
    submission = _draft(owner_id)
    assert serialize_draft_list_item(submission, actor_user_id=owner_id)["can_delete"] is True
    assert serialize_draft_list_item(submission, actor_user_id=uuid4())["can_delete"] is False


def test_draft_list_route_returns_owner_drafts_with_can_delete(monkeypatch) -> None:
    owner_id = uuid4()
    submission = _draft(owner_id)
    context = SimpleNamespace(user_id=owner_id, roles=("owner",), agency_id=None)
    db = MagicMock()
    captured: dict = {}

    def _fake_list_submissions(_db, **kwargs):
        captured.update(kwargs)
        return [(submission, None)], {"page": 1, "pageSize": 10, "total": 1, "totalPages": 1}

    monkeypatch.setattr(property_submission_routes, "list_submissions", _fake_list_submissions)
    response = property_submission_routes.list_property_submission_drafts(context, db)

    assert captured["statuses"] == {"draft"}
    assert captured["submitted_by"] == owner_id
    item = response["data"]["items"][0]
    assert item["submission_id"] == str(submission.id)
    assert item["can_delete"] is True


def test_list_submissions_filters_out_soft_deleted_rows() -> None:
    db = MagicMock()
    count_result = MagicMock()
    count_result.scalar.return_value = 0
    rows_result = MagicMock()
    rows_result.all.return_value = []
    db.execute.side_effect = [count_result, rows_result]

    list_submissions(db, page=1, page_size=10, statuses={"draft"}, submitted_by=uuid4())

    count_stmt = db.execute.call_args_list[0].args[0]
    compiled = str(count_stmt.compile(compile_kwargs={"literal_binds": False})).lower()
    assert "deleted_at" in compiled
    assert "is null" in compiled


def test_soft_deleted_draft_is_no_longer_fetchable() -> None:
    owner_id = uuid4()
    submission = _draft(owner_id)
    soft_delete_submission(submission, deleted_by=owner_id)
    assert submission.deleted_at is not None
    db = MagicMock()
    db.get.return_value = submission
    with pytest.raises(HTTPException) as exc_info:
        get_submission_or_404(db, submission.id)
    assert exc_info.value.status_code == 404
