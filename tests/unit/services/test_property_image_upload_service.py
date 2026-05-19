"""Unit tests for PropertyImageUploadService."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.exceptions.property_image_upload import PropertyImageUploadError
from app.services.property_image_upload_service import PropertyImageUploadService


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        allowed_property_image_extensions=[".jpg", ".jpeg", ".png", ".webp"],
        property_image_max_size_mb=5,
    )


def _submission(*, user_id: uuid.UUID, status: str = "draft") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        submitted_by=user_id,
        status=status,
        deleted_at=None,
    )


def _service(*, repo=None, s3=None, processor=None) -> PropertyImageUploadService:
    s3 = s3 or MagicMock()
    s3.build_public_url.return_value = "https://cdn.example.com/img.jpg"
    processor = processor or MagicMock()
    processor.process_now.return_value = True
    return PropertyImageUploadService(
        repository=repo or MagicMock(),
        s3_service=s3,
        watermark_service=MagicMock(),
        watermark_processor=processor,
        settings=_settings(),
    )


def test_upload_with_submission_id_success() -> None:
    user = SimpleNamespace(id=uuid.uuid4())
    submission = _submission(user_id=user.id)
    repo = MagicMock()
    repo.get_submission_by_id.return_value = submission
    s3 = MagicMock()
    s3.build_public_url.return_value = "https://cdn.example.com/img.jpg"
    processor = MagicMock()
    processor.process_now.return_value = True
    service = _service(repo=repo, s3=s3, processor=processor)

    out = service.upload_property_image(
        user=user,  # type: ignore[arg-type]
        file_bytes=b"raw",
        filename="photo.jpg",
        content_type="image/jpeg",
        submission_id=submission.id,
        draft_client_id=None,
    )

    assert out.url == "https://cdn.example.com/img.jpg"
    assert out.file_name == "photo.jpg"
    original_put = s3.put_object.call_args.kwargs["key"]
    assert f"{submission.id}/images/original/photo.jpg" in original_put
    processor.process_now.assert_called_once()


def test_upload_forbidden_when_not_owner() -> None:
    user = SimpleNamespace(id=uuid.uuid4())
    submission = _submission(user_id=uuid.uuid4())
    repo = MagicMock()
    repo.get_submission_by_id.return_value = submission
    service = _service(repo=repo)

    with pytest.raises(PropertyImageUploadError) as exc_info:
        service.upload_property_image(
            user=user,  # type: ignore[arg-type]
            file_bytes=b"x",
            filename="a.jpg",
            content_type="image/jpeg",
            submission_id=submission.id,
            draft_client_id=None,
        )
    assert exc_info.value.status_code == 403


def test_upload_conflict_when_finalized() -> None:
    user = SimpleNamespace(id=uuid.uuid4())
    submission = _submission(user_id=user.id, status="approved")
    repo = MagicMock()
    repo.get_submission_by_id.return_value = submission
    service = _service(repo=repo)

    with pytest.raises(PropertyImageUploadError) as exc_info:
        service.upload_property_image(
            user=user,  # type: ignore[arg-type]
            file_bytes=b"x",
            filename="a.jpg",
            content_type="image/jpeg",
            submission_id=submission.id,
            draft_client_id=None,
        )
    assert exc_info.value.status_code == 409


def test_finalize_presigned_watermarks_s3_object() -> None:
    user = SimpleNamespace(id=uuid.uuid4())
    draft_id = uuid.uuid4()
    s3 = MagicMock()
    s3.object_exists.return_value = True
    s3.build_public_url.side_effect = [
        "https://cdn.example.com/wm.jpg",
        "https://cdn.example.com/orig.jpg",
    ]
    processor = MagicMock()
    processor.process_now.return_value = True
    service = _service(s3=s3, processor=processor)

    out = service.finalize_presigned_property_image(
        user=user,  # type: ignore[arg-type]
        filename="photo.jpg",
        submission_id=None,
        draft_client_id=draft_id,
    )

    assert out.url == "https://cdn.example.com/wm.jpg"
    assert out.original_url == "https://cdn.example.com/orig.jpg"
    processor.process_now.assert_called_once()


def test_upload_draft_client_id_skips_submission_lookup() -> None:
    user = SimpleNamespace(id=uuid.uuid4())
    draft_id = uuid.uuid4()
    s3 = MagicMock()
    processor = MagicMock()
    processor.process_now.return_value = True
    service = _service(s3=s3, processor=processor)

    service.upload_property_image(
        user=user,  # type: ignore[arg-type]
        file_bytes=b"raw",
        filename="x.png",
        content_type="image/png",
        submission_id=None,
        draft_client_id=draft_id,
    )

    service._repo.get_submission_by_id.assert_not_called()
    key = s3.put_object.call_args.kwargs["key"]
    assert str(draft_id) in key
    assert "/images/original/" in key
