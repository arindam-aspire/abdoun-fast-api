"""Create Property direct-submit API response and persistence coverage."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.routes import property_submissions
from app.schemas.property_submissions import PropertySubmissionDirectSubmitRequest


def _request() -> PropertySubmissionDirectSubmitRequest:
    return PropertySubmissionDirectSubmitRequest(
        confirm_submit=True,
        payload={"media_documents": {"images": [{"url": "https://example.com/property.jpg"}]}},
    )


def _context():
    return SimpleNamespace(user_id=uuid4(), roles=("owner",), agency_id=None)


def test_direct_submit_returns_successful_submitted_response_without_draft_commit(monkeypatch) -> None:
    events: list[str] = []
    submission = SimpleNamespace(status="draft")
    db = MagicMock()
    db.commit.side_effect = lambda: events.append("commit")
    db.refresh.side_effect = lambda value: events.append("refresh")

    def create(*args, **kwargs):
        events.append("create")
        return submission

    def submit(*args, **kwargs):
        events.append("submit")
        submission.status = "submitted"
        return submission

    monkeypatch.setattr(property_submissions, "create_submission", create)
    monkeypatch.setattr(property_submissions, "submit_submission", submit)
    monkeypatch.setattr(property_submissions, "serialize_submission", lambda value: {"status": value.status})

    response = property_submissions.submit_new_property_submission(_request(), _context(), db)

    assert events == ["create", "submit", "commit", "refresh"]
    assert db.commit.call_count == 1
    assert response == {
        "success": True,
        "message": "Property submitted for approval",
        "data": {"status": "submitted"},
        "error": None,
        "meta": {},
    }


def test_direct_submit_validation_error_does_not_commit_draft(monkeypatch) -> None:
    submission = SimpleNamespace(status="draft")
    db = MagicMock()
    monkeypatch.setattr(property_submissions, "create_submission", lambda *args, **kwargs: submission)

    def reject_submission(*args, **kwargs):
        raise HTTPException(status_code=400, detail="At least one property image is required before submitting")

    monkeypatch.setattr(property_submissions, "submit_submission", reject_submission)

    with pytest.raises(HTTPException) as exc_info:
        property_submissions.submit_new_property_submission(_request(), _context(), db)

    assert exc_info.value.status_code == 400
    assert submission.status == "draft"
    db.commit.assert_not_called()
    db.refresh.assert_not_called()
