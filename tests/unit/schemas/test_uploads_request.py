"""Pydantic validation for presigned upload request."""

import uuid

import pytest
from pydantic import ValidationError

from app.schemas.uploads import PresignedUploadRequest


def test_presign_requires_submission_or_draft_id() -> None:
    with pytest.raises(ValidationError) as e:
        PresignedUploadRequest(
            context="property_media_image",
            file_name="a.jpg",
            content_type="image/jpeg",
        )
    assert "submission_id" in str(e.value).lower() or "draft" in str(e.value).lower()


def test_presign_rejects_both_ids() -> None:
    with pytest.raises(ValidationError):
        PresignedUploadRequest(
            submission_id=uuid.uuid4(),
            draft_client_id=uuid.uuid4(),
            context="property_media_image",
            file_name="a.jpg",
            content_type="image/jpeg",
        )
