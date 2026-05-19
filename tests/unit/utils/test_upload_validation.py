"""Unit tests for property image upload validation helpers."""

import uuid

import pytest

from app.exceptions.property_image_upload import PropertyImageUploadError
from app.utils.upload_validation import (
    resolve_draft_path_id,
    validate_property_image_file,
)


def test_resolve_draft_path_id_requires_xor() -> None:
    sid = uuid.uuid4()
    did = uuid.uuid4()

    assert resolve_draft_path_id(submission_id=sid, draft_client_id=None) == sid
    assert resolve_draft_path_id(submission_id=None, draft_client_id=did) == did

    with pytest.raises(PropertyImageUploadError) as both_exc:
        resolve_draft_path_id(submission_id=sid, draft_client_id=did)
    assert both_exc.value.status_code == 400

    with pytest.raises(PropertyImageUploadError) as neither_exc:
        resolve_draft_path_id(submission_id=None, draft_client_id=None)
    assert neither_exc.value.status_code == 400


def test_validate_property_image_file_rejects_empty_and_invalid() -> None:
    with pytest.raises(PropertyImageUploadError):
        validate_property_image_file(
            filename="a.jpg",
            content_type="image/jpeg",
            file_bytes=b"",
            allowed_extensions=[".jpg"],
            max_size_mb=5,
        )

    with pytest.raises(PropertyImageUploadError):
        validate_property_image_file(
            filename="a.gif",
            content_type="image/gif",
            file_bytes=b"x",
            allowed_extensions=[".jpg", ".jpeg", ".png", ".webp"],
            max_size_mb=5,
        )

    with pytest.raises(PropertyImageUploadError):
        validate_property_image_file(
            filename="a.jpg",
            content_type="application/pdf",
            file_bytes=b"x",
            allowed_extensions=[".jpg"],
            max_size_mb=5,
        )


def test_validate_property_image_file_enforces_size_limit() -> None:
    with pytest.raises(PropertyImageUploadError) as exc_info:
        validate_property_image_file(
            filename="big.jpg",
            content_type="image/jpeg",
            file_bytes=b"x" * (6 * 1024 * 1024),
            allowed_extensions=[".jpg"],
            max_size_mb=5,
        )
    assert "5 MB" in (exc_info.value.detail or "")
