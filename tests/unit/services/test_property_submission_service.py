"""Unit tests for PropertySubmissionService workflow behavior."""

import uuid
from datetime import datetime
from unittest.mock import MagicMock
from contextlib import nullcontext

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models.property_listing_submission import PropertyListingSubmission
from app.repositories.property_submission_repository import PropertySubmissionRepository
from app.services.property_submission_service import PropertySubmissionService
from app.schemas.property_submission import (
    AdminSubmissionReviewRequest,
    CreateAndSubmitPropertySubmissionRequest,
    CreatePropertySubmissionRequest,
    PropertySubmissionPatchRequest,
    PropertySubmissionSubmitRequest,
)


def _user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


def _submission(user_id: uuid.UUID) -> PropertyListingSubmission:
    return PropertyListingSubmission(
        id=uuid.uuid4(),
        submitted_by=user_id,
        status="draft",
        current_step=1,
        last_completed_step=0,
        payload={
            "basic_information": {},
            "location": {},
            "owner_information": {"owners": []},
            "property_details": {},
            "pricing": {},
            "amenities": {"feature_ids": []},
            "media_documents": {"images": [], "videos": [], "documents": [], "youtube_url": None, "virtual_tour_url": None},
            "review_submit": {},
        },
        step_completion={
            "basic_information": False,
            "location": False,
            "owner_information": False,
            "property_details": False,
            "pricing": False,
            "amenities": False,
            "media_documents": False,
            "review_submit": False,
        },
    )


@pytest.fixture
def repo() -> MagicMock:
    mock_repo = MagicMock()
    mock_repo.begin_transaction.return_value = nullcontext()
    return mock_repo


@pytest.fixture
def service(repo: MagicMock) -> PropertySubmissionService:
    return PropertySubmissionService(repo)


def test_create_submission_success(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    repo.create_submission.side_effect = lambda submission: setattr(submission, "id", uuid.uuid4())
    out = service.create_submission(user=user, body=CreatePropertySubmissionRequest())
    assert out.status == "draft"
    assert out.current_step == 1
    assert out.payload is None
    repo.commit.assert_called_once()


def test_create_submission_empty_body_uses_default(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    repo.create_submission.side_effect = lambda submission: setattr(submission, "id", uuid.uuid4())
    out = service.create_submission(user=user, body=None)
    assert out.status == "draft"
    assert out.payload is None
    assert repo.create_submission.call_count == 1


def test_create_submission_with_full_payload_draft(service: PropertySubmissionService, repo: MagicMock) -> None:
    user = _user()
    mock_type = MagicMock()
    mock_type.category_id = 1
    repo.get_category_type.return_value = mock_type
    repo.create_submission.side_effect = lambda submission: setattr(submission, "id", uuid.uuid4())
    pl = {
        "basic_information": {
            "listing_purpose": "sale",
            "category_id": 1,
            "type_id": 2,
            "title": "Hi",
        },
    }
    out = service.create_submission(
        user=user,
        body=CreatePropertySubmissionRequest(payload=pl, current_step=2),
    )
    assert out.submission_id is not None
    assert out.status == "draft"
    assert out.current_step == 2
    assert out.payload is not None
    assert out.payload.get("basic_information", {}).get("title") == "Hi"


def test_create_submission_rejects_s3_key_in_draft_images(service: PropertySubmissionService, repo: MagicMock) -> None:
    user = _user()
    pl = {
        "media_documents": {
            "images": [{"file_name": "a.jpg", "url": "https://x", "s3_key": "bad"}],
        }
    }
    with pytest.raises(HTTPException) as e:
        service.create_submission(user=user, body=CreatePropertySubmissionRequest(payload=pl))
    assert e.value.status_code == 400


def test_create_and_submit_success(service: PropertySubmissionService, repo: MagicMock) -> None:
    user = _user()
    sub = _ready_submission(user.id)
    pl = sub.payload
    body = CreateAndSubmitPropertySubmissionRequest(payload=pl, confirm_submit=True)
    repo.create_submission.side_effect = lambda submission: setattr(submission, "id", uuid.uuid4())
    mock_type = MagicMock()
    mock_type.category_id = 1
    repo.get_category_type.return_value = mock_type
    mock_area = MagicMock()
    mock_area.city_id = 1
    repo.get_area.return_value = mock_area
    repo.get_city.return_value = MagicMock()
    repo.get_owner_by_email_or_phone.return_value = None
    repo.get_user_by_phone.return_value = None
    repo.get_user_by_email.return_value = None
    repo.count_existing_features.return_value = 2
    repo.get_property.return_value = None
    repo.create_property.side_effect = lambda prop: setattr(prop, "id", uuid.uuid4())
    out = service.create_and_submit_submission(user=user, body=body)
    assert out.status == "submitted"
    assert out.property_id is not None
    assert repo.create_submission.call_count == 1


def test_create_and_submit_skips_persist_on_validation_failure(
    service: PropertySubmissionService, repo: MagicMock,
) -> None:
    user = _user()
    pl = {
        "basic_information": {
            "listing_purpose": "sale",
            "category_id": 1,
            "type_id": 2,
        },
    }
    with pytest.raises(HTTPException) as e:
        service.create_and_submit_submission(
            user=user,
            body=CreateAndSubmitPropertySubmissionRequest(payload=pl, confirm_submit=True),
        )
    assert e.value.status_code == 400
    assert not repo.create_submission.called


def test_create_and_submit_rollback_on_upsert_failure(
    service: PropertySubmissionService, repo: MagicMock,
) -> None:
    """Direct submit: persistence failure must rollback the session (no successful commit of partial property)."""
    user = _user()
    pl = _ready_submission(user.id).payload
    body = CreateAndSubmitPropertySubmissionRequest(payload=pl, confirm_submit=True)
    repo.create_submission.side_effect = lambda submission: setattr(submission, "id", uuid.uuid4())
    mock_type = MagicMock()
    mock_type.category_id = 1
    repo.get_category_type.return_value = mock_type
    mock_area = MagicMock()
    mock_area.city_id = 1
    repo.get_area.return_value = mock_area
    repo.get_city.return_value = MagicMock()
    repo.get_owner_by_email_or_phone.return_value = None
    repo.get_user_by_phone.return_value = None
    repo.get_user_by_email.return_value = None
    repo.count_existing_features.return_value = 2
    repo.get_property.return_value = None
    repo.create_property.side_effect = RuntimeError("db error")
    with pytest.raises(HTTPException) as exc_info:
        service.create_and_submit_submission(user=user, body=body)
    assert exc_info.value.status_code == 500
    repo.rollback.assert_called()
    assert not repo.commit.called


def test_get_own_submission_success(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _submission(user.id)
    repo.get_submission_by_id.return_value = submission
    out = service.get_submission(submission_id=submission.id, user=user)
    assert out.submission_id == submission.id
    assert out.status == "draft"


def test_get_other_user_submission_not_found(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _submission(uuid.uuid4())
    repo.get_submission_by_id.return_value = submission
    with pytest.raises(HTTPException) as exc_info:
        service.get_submission(submission_id=submission.id, user=user)
    assert exc_info.value.status_code == 404


def test_patch_basic_information_success(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _submission(user.id)
    repo.get_submission_by_id.return_value = submission
    mock_type = MagicMock()
    mock_type.category_id = 1
    repo.get_category_type.return_value = mock_type
    body = PropertySubmissionPatchRequest(
        step="basic_information",
        action="next",
        data={"listing_purpose": "sale", "category_id": 1, "type_id": 2, "title": "t"},
    )
    out = service.patch_submission(submission_id=submission.id, body=body, user=user)
    assert out.saved_step == "basic_information"
    assert out.current_step >= 2
    assert "basic_information" in out.payload
    assert out.payload["basic_information"].get("title") == "t"


def test_patch_owner_information_success(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _submission(user.id)
    repo.get_submission_by_id.return_value = submission
    body = PropertySubmissionPatchRequest(
        step="owner_information",
        action="save",
        data={"owners": [{"full_name": "Owner A", "phone": "+9627"}]},
    )
    out = service.patch_submission(submission_id=submission.id, body=body, user=user)
    assert out.saved_step == "owner_information"


def test_patch_owner_information_accepts_documents(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _submission(user.id)
    repo.get_submission_by_id.return_value = submission
    body = PropertySubmissionPatchRequest(
        step="owner_information",
        action="save",
        data={
            "owners": [
                {
                    "full_name": "Owner A",
                    "phone": "+9627",
                    "documents": [
                        {
                            "url": "https://doc/owner-passport.pdf",
                            "file_name": "passport.pdf",
                        }
                    ],
                }
            ]
        },
    )
    out = service.patch_submission(submission_id=submission.id, body=body, user=user)
    assert out.saved_step == "owner_information"


def test_patch_owner_information_preserves_documents_when_followup_omits_documents(
    service: PropertySubmissionService, repo: MagicMock,
) -> None:
    """Regression: list replace on owners[] used to wipe documents when FE PATCHes name/email only."""
    user = _user()
    submission = _submission(user.id)
    repo.get_submission_by_id.return_value = submission
    service.patch_submission(
        submission_id=submission.id,
        body=PropertySubmissionPatchRequest(
            step="owner_information",
            action="save",
            data={
                "owners": [
                    {
                        "full_name": "Owner A",
                        "phone": "+9627",
                        "documents": [{"url": "https://s3/a.pdf", "file_name": "a.pdf"}],
                    }
                ]
            },
        ),
        user=user,
    )
    service.patch_submission(
        submission_id=submission.id,
        body=PropertySubmissionPatchRequest(
            step="owner_information",
            action="save",
            data={"owners": [{"full_name": "Owner A", "phone": "+9627", "email": "a@example.com"}]},
        ),
        user=user,
    )
    docs = submission.payload["owner_information"]["owners"][0]["documents"]
    assert len(docs) == 1
    assert docs[0]["url"] == "https://s3/a.pdf"


def test_patch_owner_information_merges_documents_by_url_when_appending(
    service: PropertySubmissionService, repo: MagicMock,
) -> None:
    user = _user()
    submission = _submission(user.id)
    repo.get_submission_by_id.return_value = submission
    service.patch_submission(
        submission_id=submission.id,
        body=PropertySubmissionPatchRequest(
            step="owner_information",
            action="save",
            data={
                "owners": [
                    {
                        "full_name": "Owner A",
                        "phone": "+9627",
                        "documents": [{"url": "https://s3/one.pdf", "file_name": "one.pdf"}],
                    }
                ]
            },
        ),
        user=user,
    )
    service.patch_submission(
        submission_id=submission.id,
        body=PropertySubmissionPatchRequest(
            step="owner_information",
            action="save",
            data={
                "owners": [
                    {
                        "full_name": "Owner A",
                        "phone": "+9627",
                        "documents": [{"url": "https://s3/two.pdf", "file_name": "two.pdf"}],
                    }
                ]
            },
        ),
        user=user,
    )
    docs = submission.payload["owner_information"]["owners"][0]["documents"]
    urls = {d["url"] for d in docs}
    assert urls == {"https://s3/one.pdf", "https://s3/two.pdf"}


def test_patch_owner_information_explicit_empty_documents_clears(
    service: PropertySubmissionService, repo: MagicMock,
) -> None:
    user = _user()
    submission = _submission(user.id)
    repo.get_submission_by_id.return_value = submission
    service.patch_submission(
        submission_id=submission.id,
        body=PropertySubmissionPatchRequest(
            step="owner_information",
            action="save",
            data={
                "owners": [
                    {
                        "full_name": "Owner A",
                        "phone": "+9627",
                        "documents": [{"url": "https://s3/a.pdf", "file_name": "a.pdf"}],
                    }
                ]
            },
        ),
        user=user,
    )
    service.patch_submission(
        submission_id=submission.id,
        body=PropertySubmissionPatchRequest(
            step="owner_information",
            action="save",
            data={"owners": [{"full_name": "Owner A", "phone": "+9627", "documents": []}]},
        ),
        user=user,
    )
    assert submission.payload["owner_information"]["owners"][0]["documents"] == []


def test_patch_amenities_success(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _submission(user.id)
    repo.get_submission_by_id.return_value = submission
    repo.count_existing_features.return_value = 2
    body = PropertySubmissionPatchRequest(
        step="amenities",
        action="save",
        data={"feature_ids": [1, 2]},
    )
    out = service.patch_submission(submission_id=submission.id, body=body, user=user)
    assert out.saved_step == "amenities"


def test_patch_property_details_accepts_property_age_range_string(
    service: PropertySubmissionService, repo: MagicMock,
) -> None:
    """Regression: UI sends categorical age like '6-10'; must not 500 on float()."""
    user = _user()
    submission = _submission(user.id)
    repo.get_submission_by_id.return_value = submission
    body = PropertySubmissionPatchRequest(
        step="property_details",
        action="save",
        data={"property_age": "6-10", "bedrooms": 2},
    )
    out = service.patch_submission(submission_id=submission.id, body=body, user=user)
    assert out.saved_step == "property_details"
    assert submission.payload["property_details"]["property_age"] == "6-10"


def test_patch_property_details_rejects_non_numeric_bedrooms(
    service: PropertySubmissionService, repo: MagicMock,
) -> None:
    user = _user()
    submission = _submission(user.id)
    repo.get_submission_by_id.return_value = submission
    with pytest.raises(HTTPException) as exc_info:
        service.patch_submission(
            submission_id=submission.id,
            body=PropertySubmissionPatchRequest(
                step="property_details",
                action="save",
                data={"bedrooms": "not-a-number"},
            ),
            user=user,
        )
    assert exc_info.value.status_code == 400


def test_patch_media_documents_accepts_videos(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _submission(user.id)
    repo.get_submission_by_id.return_value = submission
    body = PropertySubmissionPatchRequest(
        step="media_documents",
        action="save",
        data={
            "videos": [
                {
                    "url": "https://cdn/video.mp4",
                    "file_name": "video.mp4",
                    "caption": "walkthrough",
                    "display_order": 1,
                }
            ]
        },
    )
    out = service.patch_submission(submission_id=submission.id, body=body, user=user)
    assert out.saved_step == "media_documents"


def test_patch_save_draft_keeps_draft_status(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _submission(user.id)
    repo.get_submission_by_id.return_value = submission
    body = PropertySubmissionPatchRequest(
        step="pricing",
        action="save_draft",
        data={"price": 1000, "currency": "JOD"},
    )
    out = service.patch_submission(submission_id=submission.id, body=body, user=user)
    assert out.status == "draft"


def test_patch_submitted_submission_is_locked(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _submission(user.id)
    submission.status = "submitted"
    submission.property_id = uuid.uuid4()
    repo.get_submission_by_id.return_value = submission
    body = PropertySubmissionPatchRequest(
        step="pricing",
        action="save_draft",
        data={"price": 1000},
    )
    with pytest.raises(HTTPException) as exc_info:
        service.patch_submission(submission_id=submission.id, body=body, user=user)
    assert exc_info.value.status_code == 409


def test_patch_approved_submission_is_locked(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _submission(user.id)
    submission.status = "approved"
    repo.get_submission_by_id.return_value = submission
    body = PropertySubmissionPatchRequest(step="pricing", action="save", data={"price": 1000})
    with pytest.raises(HTTPException) as exc_info:
        service.patch_submission(submission_id=submission.id, body=body, user=user)
    assert exc_info.value.status_code == 409


def test_patch_changes_requested_submission_is_editable(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _submission(user.id)
    submission.status = "changes_requested"
    repo.get_submission_by_id.return_value = submission
    body = PropertySubmissionPatchRequest(step="pricing", action="save", data={"price": 1000, "currency": "JOD"})
    out = service.patch_submission(submission_id=submission.id, body=body, user=user)
    assert out.status == "changes_requested"


def test_submit_fails_when_required_missing(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _submission(user.id)
    repo.get_submission_by_id.return_value = submission
    with pytest.raises(HTTPException) as exc_info:
        service.submit_submission(
            submission_id=submission.id,
            body=PropertySubmissionSubmitRequest(confirm_submit=True),
            user=user,
        )
    assert exc_info.value.status_code == 400


def _ready_submission(user_id: uuid.UUID) -> PropertyListingSubmission:
    submission = _submission(user_id)
    submission.payload["basic_information"] = {
        "listing_purpose": "sale",
        "category_id": 1,
        "type_id": 2,
        "title": "Villa",
        "description": "Desc",
    }
    submission.payload["location"] = {"city_id": 1, "area_id": 1, "address": "Addr"}
    submission.payload["owner_information"] = {
        "owners": [
            {
                "full_name": "O",
                "phone": "+1",
                "is_primary": True,
                "documents": [{"url": "https://owner/doc.pdf", "file_name": "doc.pdf"}],
            }
        ]
    }
    submission.payload["pricing"] = {"price": 250000, "currency": "JOD"}
    submission.payload["property_details"] = {"bedrooms": 4, "bathrooms": 3}
    submission.payload["amenities"] = {"feature_ids": [1, 2]}
    submission.payload["media_documents"] = {
        "images": [{"url": "https://img/1.jpg", "file_name": "1.jpg", "is_primary": True, "display_order": 0}],
        "videos": [{"url": "https://vid/1.mp4", "file_name": "1.mp4", "display_order": 1, "caption": "walkthrough"}],
        "documents": [{"url": "https://doc/1.pdf", "file_name": "doc.pdf"}],
        "youtube_url": "https://youtube.com/watch?v=abc",
        "virtual_tour_url": "https://tour.example/1",
    }
    submission.payload["review_submit"] = {
        "terms_accepted": True,
        "privacy_accepted": True,
        "public_display_authorized": True,
        "fees_acknowledged": True,
    }
    submission.terms_accepted = True
    submission.privacy_accepted = True
    submission.public_display_authorized = True
    submission.fees_acknowledged = True
    return submission


def test_submit_succeeds_with_valid_payload(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _ready_submission(user.id)
    repo.get_submission_by_id.return_value = submission
    mock_type = MagicMock()
    mock_type.category_id = 1
    repo.get_category_type.return_value = mock_type
    mock_city = MagicMock()
    repo.get_city.return_value = mock_city
    mock_area = MagicMock()
    mock_area.city_id = 1
    repo.get_area.return_value = mock_area
    repo.get_owner_by_email_or_phone.return_value = None
    repo.get_user_by_phone.return_value = None
    repo.get_user_by_email.return_value = None
    repo.count_existing_features.return_value = 2
    repo.get_property.return_value = None

    created_property = MagicMock()
    created_property.id = uuid.uuid4()
    created_property.updated_at = datetime.utcnow()

    def _create_property(prop):
        prop.id = created_property.id
        prop.updated_at = created_property.updated_at
        return prop

    repo.create_property.side_effect = _create_property
    out = service.submit_submission(
        submission_id=submission.id,
        body=PropertySubmissionSubmitRequest(confirm_submit=True),
        user=user,
    )
    assert out.status == "submitted"
    repo.begin_transaction.assert_called_once()


def test_submit_creates_property_row(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _ready_submission(user.id)
    repo.get_submission_by_id.return_value = submission
    mock_type = MagicMock()
    mock_type.category_id = 1
    repo.get_category_type.return_value = mock_type
    mock_area = MagicMock()
    mock_area.city_id = 1
    repo.get_area.return_value = mock_area
    repo.get_owner_by_email_or_phone.return_value = None
    repo.get_user_by_phone.return_value = None
    repo.get_user_by_email.return_value = None
    repo.get_city.return_value = MagicMock()
    repo.count_existing_features.return_value = 2
    repo.get_property.return_value = None
    repo.create_property.side_effect = lambda prop: setattr(prop, "id", uuid.uuid4())
    service.submit_submission(
        submission_id=submission.id,
        body=PropertySubmissionSubmitRequest(confirm_submit=True),
        user=user,
    )
    assert repo.create_property.called


def test_submit_creates_owner_and_property_owner_rows(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _ready_submission(user.id)
    repo.get_submission_by_id.return_value = submission
    mock_type = MagicMock()
    mock_type.category_id = 1
    repo.get_category_type.return_value = mock_type
    mock_area = MagicMock()
    mock_area.city_id = 1
    repo.get_area.return_value = mock_area
    repo.get_owner_by_email_or_phone.return_value = None
    repo.get_user_by_phone.return_value = None
    repo.get_user_by_email.return_value = None
    repo.get_city.return_value = MagicMock()
    repo.count_existing_features.return_value = 2
    repo.get_property.return_value = None
    repo.create_property.side_effect = lambda prop: setattr(prop, "id", uuid.uuid4())
    service.submit_submission(
        submission_id=submission.id,
        body=PropertySubmissionSubmitRequest(confirm_submit=True),
        user=user,
    )
    assert repo.add_owner.called
    assert repo.add_property_owner.called


def test_submit_creates_property_features_rows(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _ready_submission(user.id)
    repo.get_submission_by_id.return_value = submission
    mock_type = MagicMock()
    mock_type.category_id = 1
    repo.get_category_type.return_value = mock_type
    mock_area = MagicMock()
    mock_area.city_id = 1
    repo.get_area.return_value = mock_area
    repo.get_owner_by_email_or_phone.return_value = None
    repo.get_user_by_phone.return_value = None
    repo.get_user_by_email.return_value = None
    repo.get_city.return_value = MagicMock()
    repo.count_existing_features.return_value = 2
    repo.get_property.return_value = None
    repo.create_property.side_effect = lambda prop: setattr(prop, "id", uuid.uuid4())
    service.submit_submission(
        submission_id=submission.id,
        body=PropertySubmissionSubmitRequest(confirm_submit=True),
        user=user,
    )
    assert repo.add_property_feature.called


def test_submit_creates_property_media_rows(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _ready_submission(user.id)
    repo.get_submission_by_id.return_value = submission
    mock_type = MagicMock()
    mock_type.category_id = 1
    repo.get_category_type.return_value = mock_type
    mock_area = MagicMock()
    mock_area.city_id = 1
    repo.get_area.return_value = mock_area
    repo.get_owner_by_email_or_phone.return_value = None
    repo.get_user_by_phone.return_value = None
    repo.get_user_by_email.return_value = None
    repo.get_city.return_value = MagicMock()
    repo.count_existing_features.return_value = 2
    repo.get_property.return_value = None
    repo.create_property.side_effect = lambda prop: setattr(prop, "id", uuid.uuid4())
    service.submit_submission(
        submission_id=submission.id,
        body=PropertySubmissionSubmitRequest(confirm_submit=True),
        user=user,
    )
    assert repo.add_property_media.called


def test_submit_rollback_on_failure(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _ready_submission(user.id)
    repo.get_submission_by_id.return_value = submission
    mock_type = MagicMock()
    mock_type.category_id = 1
    repo.get_category_type.return_value = mock_type
    mock_area = MagicMock()
    mock_area.city_id = 1
    repo.get_area.return_value = mock_area
    repo.get_owner_by_email_or_phone.return_value = None
    repo.get_user_by_phone.return_value = None
    repo.get_user_by_email.return_value = None
    repo.get_city.return_value = MagicMock()
    repo.count_existing_features.return_value = 2
    repo.get_property.return_value = None
    repo.create_property.side_effect = RuntimeError("db error")
    with pytest.raises(HTTPException) as exc_info:
        service.submit_submission(
            submission_id=submission.id,
            body=PropertySubmissionSubmitRequest(confirm_submit=True),
            user=user,
        )
    assert exc_info.value.status_code == 500
    repo.rollback.assert_called_once()


def test_submit_persists_owner_documents(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _ready_submission(user.id)
    repo.get_submission_by_id.return_value = submission
    mock_type = MagicMock()
    mock_type.category_id = 1
    repo.get_category_type.return_value = mock_type
    mock_area = MagicMock()
    mock_area.city_id = 1
    repo.get_area.return_value = mock_area
    repo.get_city.return_value = MagicMock()
    repo.count_existing_features.return_value = 2
    repo.get_property.return_value = None
    repo.get_owner_by_email_or_phone.return_value = None
    repo.get_user_by_phone.return_value = None
    repo.get_user_by_email.return_value = None
    repo.create_property.side_effect = lambda prop: setattr(prop, "id", uuid.uuid4())
    service.submit_submission(
        submission_id=submission.id,
        body=PropertySubmissionSubmitRequest(confirm_submit=True),
        user=user,
    )
    owner_obj = repo.add_owner.call_args[0][0]
    assert owner_obj.documents and owner_obj.documents[0]["url"] == "https://owner/doc.pdf"


def test_submit_links_owner_user_id_when_email_matches(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _ready_submission(user.id)
    submission.payload["owner_information"]["owners"][0]["email"] = "owner@example.com"
    repo.get_submission_by_id.return_value = submission
    mock_type = MagicMock()
    mock_type.category_id = 1
    repo.get_category_type.return_value = mock_type
    mock_area = MagicMock()
    mock_area.city_id = 1
    repo.get_area.return_value = mock_area
    repo.get_city.return_value = MagicMock()
    repo.count_existing_features.return_value = 2
    repo.get_property.return_value = None
    repo.get_owner_by_email_or_phone.return_value = None
    matched_user = MagicMock()
    matched_user.id = uuid.uuid4()
    repo.get_user_by_email.return_value = matched_user
    repo.get_user_by_phone.return_value = None
    repo.create_property.side_effect = lambda prop: setattr(prop, "id", uuid.uuid4())
    service.submit_submission(
        submission_id=submission.id,
        body=PropertySubmissionSubmitRequest(confirm_submit=True),
        user=user,
    )
    owner_obj = repo.add_owner.call_args[0][0]
    assert owner_obj.user_id == matched_user.id


def test_submit_links_owner_user_id_when_phone_matches(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _ready_submission(user.id)
    repo.get_submission_by_id.return_value = submission
    mock_type = MagicMock()
    mock_type.category_id = 1
    repo.get_category_type.return_value = mock_type
    mock_area = MagicMock()
    mock_area.city_id = 1
    repo.get_area.return_value = mock_area
    repo.get_city.return_value = MagicMock()
    repo.count_existing_features.return_value = 2
    repo.get_property.return_value = None
    repo.get_owner_by_email_or_phone.return_value = None
    matched_user = MagicMock()
    matched_user.id = uuid.uuid4()
    repo.get_user_by_email.return_value = None
    repo.get_user_by_phone.return_value = matched_user
    repo.create_property.side_effect = lambda prop: setattr(prop, "id", uuid.uuid4())
    service.submit_submission(
        submission_id=submission.id,
        body=PropertySubmissionSubmitRequest(confirm_submit=True),
        user=user,
    )
    owner_obj = repo.add_owner.call_args[0][0]
    assert owner_obj.user_id == matched_user.id


def test_submit_fails_when_owner_email_phone_match_different_users(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _ready_submission(user.id)
    submission.payload["owner_information"]["owners"][0]["email"] = "owner@example.com"
    repo.get_submission_by_id.return_value = submission
    mock_type = MagicMock()
    mock_type.category_id = 1
    repo.get_category_type.return_value = mock_type
    mock_area = MagicMock()
    mock_area.city_id = 1
    repo.get_area.return_value = mock_area
    repo.get_city.return_value = MagicMock()
    repo.count_existing_features.return_value = 2
    repo.get_property.return_value = None
    repo.get_owner_by_email_or_phone.return_value = None
    user_a = MagicMock()
    user_a.id = uuid.uuid4()
    user_b = MagicMock()
    user_b.id = uuid.uuid4()
    repo.get_user_by_email.return_value = user_a
    repo.get_user_by_phone.return_value = user_b
    repo.create_property.side_effect = lambda prop: setattr(prop, "id", uuid.uuid4())
    with pytest.raises(HTTPException) as exc_info:
        service.submit_submission(
            submission_id=submission.id,
            body=PropertySubmissionSubmitRequest(confirm_submit=True),
            user=user,
        )
    assert exc_info.value.status_code == 400


def test_submit_persists_videos_and_documents_as_property_media(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _ready_submission(user.id)
    repo.get_submission_by_id.return_value = submission
    mock_type = MagicMock()
    mock_type.category_id = 1
    repo.get_category_type.return_value = mock_type
    mock_area = MagicMock()
    mock_area.city_id = 1
    repo.get_area.return_value = mock_area
    repo.get_city.return_value = MagicMock()
    repo.count_existing_features.return_value = 2
    repo.get_property.return_value = None
    repo.get_owner_by_email_or_phone.return_value = None
    repo.get_user_by_email.return_value = None
    repo.get_user_by_phone.return_value = None
    repo.create_property.side_effect = lambda prop: setattr(prop, "id", uuid.uuid4())
    service.submit_submission(
        submission_id=submission.id,
        body=PropertySubmissionSubmitRequest(confirm_submit=True),
        user=user,
    )
    media_types = [call_args[0][0].media_type for call_args in repo.add_property_media.call_args_list]
    assert "image" in media_types
    assert "video" in media_types
    assert "document" in media_types
    repo.replace_property_media.assert_called_once()


def test_submit_twice_returns_same_property_without_reprocessing(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _ready_submission(user.id)
    submission.status = "submitted"
    submission.property_id = uuid.uuid4()
    repo.get_submission_by_id.return_value = submission
    out = service.submit_submission(
        submission_id=submission.id,
        body=PropertySubmissionSubmitRequest(confirm_submit=True),
        user=user,
    )
    assert out.property_id == submission.property_id
    assert not repo.create_property.called


def test_resubmit_from_changes_requested_moves_back_to_submitted(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _ready_submission(user.id)
    submission.status = "changes_requested"
    repo.get_submission_by_id.return_value = submission
    mock_type = MagicMock()
    mock_type.category_id = 1
    repo.get_category_type.return_value = mock_type
    mock_area = MagicMock()
    mock_area.city_id = 1
    repo.get_area.return_value = mock_area
    repo.get_city.return_value = MagicMock()
    repo.count_existing_features.return_value = 2
    repo.get_property.return_value = None
    repo.get_owner_by_email_or_phone.return_value = None
    repo.get_user_by_email.return_value = None
    repo.get_user_by_phone.return_value = None
    repo.create_property.side_effect = lambda prop: setattr(prop, "id", uuid.uuid4())
    out = service.submit_submission(
        submission_id=submission.id,
        body=PropertySubmissionSubmitRequest(confirm_submit=True),
        user=user,
    )
    assert out.status == "submitted"


def test_resubmit_from_rejected_moves_back_to_submitted_and_clears_review(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _ready_submission(user.id)
    submission.status = "rejected"
    submission.review_reason = "Needs better photos"
    submission.reviewed_at = datetime.now()
    repo.get_submission_by_id.return_value = submission
    mock_type = MagicMock()
    mock_type.category_id = 1
    repo.get_category_type.return_value = mock_type
    mock_area = MagicMock()
    mock_area.city_id = 1
    repo.get_area.return_value = mock_area
    repo.get_city.return_value = MagicMock()
    repo.count_existing_features.return_value = 2
    repo.get_property.return_value = None
    repo.get_owner_by_email_or_phone.return_value = None
    repo.get_user_by_email.return_value = None
    repo.get_user_by_phone.return_value = None
    repo.create_property.side_effect = lambda prop: setattr(prop, "id", uuid.uuid4())
    out = service.submit_submission(
        submission_id=submission.id,
        body=PropertySubmissionSubmitRequest(confirm_submit=True),
        user=user,
    )
    assert out.status == "submitted"
    assert submission.review_reason is None
    assert submission.reviewed_at is None


def test_patch_rejected_allows_editing(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _submission(user.id)
    submission.status = "rejected"
    repo.get_submission_by_id.return_value = submission
    body = PropertySubmissionPatchRequest(step="pricing", action="save", data={"price": 1000, "currency": "JOD"})
    out = service.patch_submission(submission_id=submission.id, body=body, user=user)
    assert out.status == "rejected"


def test_delete_rejected_succeeds(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _submission(user.id)
    submission.status = "rejected"
    submission.property_id = uuid.uuid4()
    repo.get_submission_by_id.return_value = submission
    out = service.delete_submission(submission_id=submission.id, user=user)
    assert out.submission_id == submission.id
    assert out.property_id == submission.property_id
    repo.delete_submission_and_property.assert_called_once()
    repo.commit.assert_called_once()


def test_delete_submitted_is_blocked(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _submission(user.id)
    submission.status = "submitted"
    submission.property_id = uuid.uuid4()
    repo.get_submission_by_id.return_value = submission
    with pytest.raises(HTTPException) as exc_info:
        service.delete_submission(submission_id=submission.id, user=user)
    assert exc_info.value.status_code == 409
    repo.delete_submission_and_property.assert_not_called()


def test_same_owner_reused_across_submissions(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _ready_submission(user.id)
    repo.get_submission_by_id.return_value = submission
    mock_type = MagicMock()
    mock_type.category_id = 1
    repo.get_category_type.return_value = mock_type
    mock_area = MagicMock()
    mock_area.city_id = 1
    repo.get_area.return_value = mock_area
    repo.get_city.return_value = MagicMock()
    repo.count_existing_features.return_value = 2
    repo.get_property.return_value = None
    repo.get_user_by_email.return_value = None
    repo.get_user_by_phone.return_value = None
    existing_owner = MagicMock()
    existing_owner.owner_id = uuid.uuid4()
    existing_owner.full_name = "Existing"
    existing_owner.nationality = None
    existing_owner.ssi = None
    existing_owner.address = None
    existing_owner.documents = [{"url": "https://old/doc.pdf"}]
    repo.get_owner_by_email_or_phone.return_value = existing_owner
    repo.create_property.side_effect = lambda prop: setattr(prop, "id", uuid.uuid4())
    service.submit_submission(
        submission_id=submission.id,
        body=PropertySubmissionSubmitRequest(confirm_submit=True),
        user=user,
    )
    assert not repo.add_owner.called
    assert repo.add_property_owner.called


def test_patch_uses_deep_merge_without_overwrite(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _submission(user.id)
    submission.payload["property_details"] = {"nested": {"a": 1, "b": 2}, "arr": [1, 2]}
    repo.get_submission_by_id.return_value = submission
    body = PropertySubmissionPatchRequest(
        step="property_details",
        action="save",
        data={"nested": {"a": 10}, "arr": [3]},
    )
    service.patch_submission(submission_id=submission.id, body=body, user=user)
    assert submission.payload["property_details"]["nested"]["a"] == 10
    assert submission.payload["property_details"]["nested"]["b"] == 2
    assert submission.payload["property_details"]["arr"] == [3]


def test_step_completion_is_false_for_incomplete_basic_information(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _submission(user.id)
    repo.get_submission_by_id.return_value = submission
    body = PropertySubmissionPatchRequest(
        step="basic_information",
        action="save",
        data={"listing_purpose": "sale"},
    )
    out = service.patch_submission(submission_id=submission.id, body=body, user=user)
    assert out.step_completion["basic_information"] is False


def test_validation_fails_for_invalid_category_type_mapping(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _submission(user.id)
    repo.get_submission_by_id.return_value = submission
    mock_type = MagicMock()
    mock_type.category_id = 999
    repo.get_category_type.return_value = mock_type
    body = PropertySubmissionPatchRequest(
        step="basic_information",
        action="save",
        data={"category_id": 1, "type_id": 2},
    )
    with pytest.raises(HTTPException) as exc_info:
        service.patch_submission(submission_id=submission.id, body=body, user=user)
    assert exc_info.value.status_code == 400


def test_submit_uses_single_transaction_scope(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _ready_submission(user.id)
    repo.get_submission_by_id.return_value = submission
    mock_type = MagicMock()
    mock_type.category_id = 1
    repo.get_category_type.return_value = mock_type
    mock_area = MagicMock()
    mock_area.city_id = 1
    repo.get_area.return_value = mock_area
    repo.get_city.return_value = MagicMock()
    repo.count_existing_features.return_value = 2
    repo.get_property.return_value = None
    repo.get_owner_by_email_or_phone.return_value = None
    repo.get_user_by_email.return_value = None
    repo.get_user_by_phone.return_value = None
    repo.create_property.side_effect = lambda prop: setattr(prop, "id", uuid.uuid4())
    service.submit_submission(
        submission_id=submission.id,
        body=PropertySubmissionSubmitRequest(confirm_submit=True),
        user=user,
    )
    repo.begin_transaction.assert_called_once()


def test_submit_reprocesses_when_submitted_but_property_id_missing(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _ready_submission(user.id)
    submission.status = "submitted"
    submission.property_id = None
    repo.get_submission_by_id.return_value = submission
    mock_type = MagicMock()
    mock_type.category_id = 1
    repo.get_category_type.return_value = mock_type
    mock_area = MagicMock()
    mock_area.city_id = 1
    repo.get_area.return_value = mock_area
    repo.get_city.return_value = MagicMock()
    repo.count_existing_features.return_value = 2
    repo.get_property.return_value = None
    repo.get_owner_by_email_or_phone.return_value = None
    repo.get_user_by_email.return_value = None
    repo.get_user_by_phone.return_value = None
    repo.create_property.side_effect = lambda prop: setattr(prop, "id", uuid.uuid4())
    out = service.submit_submission(
        submission_id=submission.id,
        body=PropertySubmissionSubmitRequest(confirm_submit=True),
        user=user,
    )
    assert out.property_id is not None
    assert repo.create_property.called


def test_owner_create_integrity_conflict_fallback_reuses_owner(service: PropertySubmissionService, repo: MagicMock):
    user = _user()
    submission = _ready_submission(user.id)
    repo.get_submission_by_id.return_value = submission
    mock_type = MagicMock()
    mock_type.category_id = 1
    repo.get_category_type.return_value = mock_type
    mock_area = MagicMock()
    mock_area.city_id = 1
    repo.get_area.return_value = mock_area
    repo.get_city.return_value = MagicMock()
    repo.count_existing_features.return_value = 2
    repo.get_property.return_value = None
    repo.get_user_by_email.return_value = None
    repo.get_user_by_phone.return_value = None
    existing_owner = MagicMock()
    existing_owner.owner_id = uuid.uuid4()
    existing_owner.full_name = "Existing"
    existing_owner.nationality = None
    existing_owner.ssi = None
    existing_owner.address = None
    existing_owner.documents = []
    repo.get_owner_by_email_or_phone.side_effect = [None, existing_owner]
    repo.create_property.side_effect = lambda prop: setattr(prop, "id", uuid.uuid4())
    from sqlalchemy.exc import IntegrityError
    call_count = {"n": 0}
    def _flush():
        call_count["n"] += 1
        if call_count["n"] == 3:
            raise IntegrityError("insert", {}, Exception("duplicate"))
    repo.flush.side_effect = _flush
    service.submit_submission(
        submission_id=submission.id,
        body=PropertySubmissionSubmitRequest(confirm_submit=True),
        user=user,
    )
    assert repo.add_property_owner.called


def test_owner_document_merge_deduplicates_by_url(service: PropertySubmissionService):
    existing = [{"url": "https://doc/a.pdf", "name": "old-a"}, {"url": "https://doc/b.pdf"}]
    incoming = [{"url": "https://doc/a.pdf", "name": "new-a"}, {"url": "https://doc/c.pdf"}]
    merged = service._merge_owner_documents(existing, incoming)
    urls = [doc["url"] for doc in merged]
    assert len(urls) == 3
    assert set(urls) == {"https://doc/a.pdf", "https://doc/b.pdf", "https://doc/c.pdf"}


def test_submit_logging_does_not_break_flow(service: PropertySubmissionService, repo: MagicMock, monkeypatch):
    user = _user()
    submission = _ready_submission(user.id)
    repo.get_submission_by_id.return_value = submission
    mock_type = MagicMock()
    mock_type.category_id = 1
    repo.get_category_type.return_value = mock_type
    mock_area = MagicMock()
    mock_area.city_id = 1
    repo.get_area.return_value = mock_area
    repo.get_city.return_value = MagicMock()
    repo.count_existing_features.return_value = 2
    repo.get_property.return_value = None
    repo.get_owner_by_email_or_phone.return_value = None
    repo.get_user_by_email.return_value = None
    repo.get_user_by_phone.return_value = None
    repo.create_property.side_effect = lambda prop: setattr(prop, "id", uuid.uuid4())
    from app.services import property_submission_service as svc_mod
    monkeypatch.setattr(svc_mod.service_logger, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(svc_mod.service_logger, "exception", lambda *args, **kwargs: None)
    out = service.submit_submission(
        submission_id=submission.id,
        body=PropertySubmissionSubmitRequest(confirm_submit=True),
        user=user,
    )
    assert out.status == "submitted"


def test_admin_review_changes_requested_requires_reason(service: PropertySubmissionService, repo: MagicMock):
    admin = _user()
    submission = _ready_submission(uuid.uuid4())
    submission.status = "submitted"
    repo.get_submission_by_id.return_value = submission
    with pytest.raises(HTTPException) as exc_info:
        service.review_submission(
            submission_id=submission.id,
            admin_user=admin,
            body=AdminSubmissionReviewRequest(action="changes_requested", reason=None),
        )
    assert exc_info.value.status_code == 400


def test_admin_review_reject_requires_reason(service: PropertySubmissionService, repo: MagicMock):
    admin = _user()
    submission = _ready_submission(uuid.uuid4())
    submission.status = "submitted"
    repo.get_submission_by_id.return_value = submission
    with pytest.raises(HTTPException) as exc_info:
        service.review_submission(
            submission_id=submission.id,
            admin_user=admin,
            body=AdminSubmissionReviewRequest(action="reject", reason=""),
        )
    assert exc_info.value.status_code == 400


def test_admin_review_approve_success(service: PropertySubmissionService, repo: MagicMock):
    admin = _user()
    submission = _ready_submission(uuid.uuid4())
    submission.status = "submitted"
    submission.property_id = uuid.uuid4()
    repo.get_submission_by_id.return_value = submission
    property_obj = MagicMock()
    property_obj.property_status_id = 2
    repo.get_property.return_value = property_obj
    out = service.review_submission(
        submission_id=submission.id,
        admin_user=admin,
        body=AdminSubmissionReviewRequest(action="approve", reason=None),
    )
    assert out.status == "approved"
    assert property_obj.property_status_id == 1


def test_admin_review_on_draft_disallowed(service: PropertySubmissionService, repo: MagicMock):
    admin = _user()
    submission = _ready_submission(uuid.uuid4())
    submission.status = "draft"
    repo.get_submission_by_id.return_value = submission
    with pytest.raises(HTTPException) as exc_info:
        service.review_submission(
            submission_id=submission.id,
            admin_user=admin,
            body=AdminSubmissionReviewRequest(action="approve", reason=None),
        )
    assert exc_info.value.status_code == 409


def test_step_completion_empty_title_marks_basic_false(service: PropertySubmissionService) -> None:
    svc = PropertySubmissionService(MagicMock())
    data = {
        "listing_purpose": "sale",
        "category_id": 1,
        "type_id": 1,
        "title": "   ",
        "description": "x",
    }
    assert svc._validate_step_completion("basic_information", data) is False  # type: ignore[arg-type]


def test_step_completion_empty_owner_name_false(service: PropertySubmissionService) -> None:
    svc = PropertySubmissionService(MagicMock())
    data = {
        "owners": [{"full_name": "", "phone": "+9627000000"}],
    }
    assert svc._validate_step_completion("owner_information", data) is False  # type: ignore[arg-type]


def test_step_completion_owner_email_only_ok(service: PropertySubmissionService) -> None:
    svc = PropertySubmissionService(MagicMock())
    data = {
        "owners": [
            {
                "full_name": "A",
                "email": "a@example.com",
            }
        ],
    }
    assert svc._validate_step_completion("owner_information", data) is True  # type: ignore[arg-type]


def test_step_completion_location_needs_address(service: PropertySubmissionService) -> None:
    svc = PropertySubmissionService(MagicMock())
    assert (
        svc._validate_step_completion(
            "location",
            {"city_id": 1, "area_id": 1, "address": "  "},
        )
        is False
    )
    assert (
        svc._validate_step_completion(
            "location",
            {"city_id": 1, "area_id": 1, "address": "Street 1"},
        )
        is True
    )


def test_step_completion_amenities_needs_one_feature(service: PropertySubmissionService) -> None:
    svc = PropertySubmissionService(MagicMock())
    assert svc._validate_step_completion("amenities", {"feature_ids": []}) is False  # type: ignore[arg-type]
    assert svc._validate_step_completion("amenities", {"feature_ids": [1]}) is True  # type: ignore[arg-type]


def test_step_completion_media_needs_file_or_link(service: PropertySubmissionService) -> None:
    svc = PropertySubmissionService(MagicMock())
    empty = {
        "images": [],
        "videos": [],
        "documents": [],
        "youtube_url": None,
        "virtual_tour_url": None,
    }
    assert svc._validate_step_completion("media_documents", empty) is False  # type: ignore[arg-type]
    with_img = {
        **empty,
        "images": [{"url": "https://s3/f.jpg", "file_name": "f.jpg"}],
    }
    assert svc._validate_step_completion("media_documents", with_img) is True  # type: ignore[arg-type]
    with_tube = {**empty, "youtube_url": "https://youtube.com/watch?v=1"}
    assert svc._validate_step_completion("media_documents", with_tube) is True  # type: ignore[arg-type]


def test_step_completion_property_details_empty_dict_false(service: PropertySubmissionService) -> None:
    svc = PropertySubmissionService(MagicMock())
    assert svc._validate_step_completion("property_details", {}) is False  # type: ignore[arg-type]


def test_step_completion_pricing_zero_false(service: PropertySubmissionService) -> None:
    svc = PropertySubmissionService(MagicMock())
    assert svc._validate_step_completion("pricing", {"price": 0, "currency": "JOD"}) is False  # type: ignore[arg-type]
    assert svc._validate_step_completion("pricing", {"price": 1, "currency": "JOD"}) is True  # type: ignore[arg-type]


def test_step_completion_review_all_false(service: PropertySubmissionService) -> None:
    svc = PropertySubmissionService(MagicMock())
    r = {k: False for k in ("terms_accepted", "privacy_accepted", "public_display_authorized", "fees_acknowledged")}
    assert svc._validate_step_completion("review_submit", r) is False  # type: ignore[arg-type]
    r2 = {k: True for k in r}
    assert svc._validate_step_completion("review_submit", r2) is True  # type: ignore[arg-type]


def test_step_completion_ready_payload_all_steps_true(
    service: PropertySubmissionService, repo: MagicMock,
) -> None:
    pl = _ready_submission(_user().id).payload
    m = service._compute_step_completion_map(pl)
    for step in [
        "basic_information",
        "location",
        "owner_information",
        "property_details",
        "pricing",
        "amenities",
        "media_documents",
    ]:
        assert m[step] is True, step
    assert m["review_submit"] is True


def test_patch_request_payload_requires_save_draft_action() -> None:
    with pytest.raises(ValidationError):
        PropertySubmissionPatchRequest(
            action="next",
            payload={"basic_information": {"title": "x"}},
            current_step=1,
        )


def test_patch_request_rejects_step_with_payload() -> None:
    with pytest.raises(ValidationError):
        PropertySubmissionPatchRequest(
            step="basic_information",
            action="save_draft",
            payload={"basic_information": {"title": "x"}},
            current_step=1,
        )


def test_patch_full_payload_save_draft_without_step(
    service: PropertySubmissionService, repo: MagicMock,
) -> None:
    """Redux-style: PATCH with whole ``payload`` + ``action=save_draft`` + ``current_step`` (no per-step ``step``)."""
    user = _user()
    submission = _submission(user.id)
    repo.get_submission_by_id.return_value = submission
    mock_type = MagicMock()
    mock_type.category_id = 1
    repo.get_category_type.return_value = mock_type
    mock_area = MagicMock()
    mock_area.city_id = 1
    repo.get_area.return_value = mock_area
    repo.get_city.return_value = MagicMock()
    repo.count_existing_features.return_value = 1
    pl = {
        "basic_information": {
            "listing_purpose": "rent",
            "category_id": 1,
            "type_id": 1,
            "title": "rented apartment",
            "description": "",
        },
        "location": {"city_id": 1, "area_id": 1, "address": ""},
        "owner_information": {
            "owners": [
                {
                    "full_name": "Jane",
                    "phone": "+962700000000",
                    "email": "a@b.com",
                    "documents": [],
                }
            ]
        },
        "property_details": {"bedrooms": 2},
        "pricing": {"price": 100, "currency": "JOD"},
        "amenities": {"feature_ids": [1]},
        "media_documents": {"images": [], "videos": [], "documents": []},
        "review_submit": {
            "terms_accepted": False,
            "privacy_accepted": False,
            "fees_acknowledged": False,
            "public_display_authorized": False,
        },
    }
    body = PropertySubmissionPatchRequest(
        action="save_draft",
        payload=pl,
        current_step=5,
    )
    out = service.patch_submission(submission_id=submission.id, body=body, user=user)
    assert out.current_step == 5
    assert out.saved_step == "pricing"
    assert out.payload["basic_information"]["title"] == "rented apartment"


def test_get_submission_recomputes_step_completion_from_payload(
    service: PropertySubmissionService, repo: MagicMock,
) -> None:
    """GET returns up-to-date flags derived from current payload (fixes stale DB rows)."""
    user = _user()
    submission = _ready_submission(user.id)
    submission.step_completion = {k: True for k in (submission.step_completion or {})}
    submission.last_completed_step = 7
    submission.payload["basic_information"]["title"] = "   "
    repo.get_submission_by_id.return_value = submission
    out = service.get_submission(submission_id=submission.id, user=user)
    assert out.step_completion.get("basic_information") is False
    assert any(v is False for v in (out.step_completion or {}).values())


def test_admin_visible_submission_statuses_exclude_drafts() -> None:
    assert "draft" not in PropertySubmissionRepository.ADMIN_VISIBLE_SUBMISSION_STATUSES
    assert "in_progress" not in PropertySubmissionRepository.ADMIN_VISIBLE_SUBMISSION_STATUSES
    assert set(PropertySubmissionRepository.ADMIN_VISIBLE_SUBMISSION_STATUSES) == {
        "submitted",
        "changes_requested",
        "approved",
        "rejected",
    }


def test_list_admin_submissions_rejects_draft_status_query_param(
    service: PropertySubmissionService,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        service.list_admin_submissions(status="draft", page=1, limit=10)
    assert exc_info.value.status_code == 400
