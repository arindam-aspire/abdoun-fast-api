"""Unit tests for UploadService presigned URL workflow."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.schemas.uploads import PresignedUploadRequest
from app.services.upload_service import UploadService


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        aws_s3_presigned_expiry=900,
        allowed_property_image_extensions=[".jpg", ".jpeg", ".png", ".webp"],
        allowed_property_video_extensions=[".mp4", ".mov", ".webm"],
        allowed_property_document_extensions=[".pdf", ".doc", ".docx"],
        property_image_max_size_mb=20,
        property_video_max_size_mb=100,
        property_document_max_size_mb=20,
    )


def _submission(user_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), submitted_by=user_id, status="draft", deleted_at=None)


def test_presigned_url_generation_for_each_context() -> None:
    user = SimpleNamespace(id=uuid.uuid4())
    repo = MagicMock()
    s3 = MagicMock()
    settings = _settings()
    submission = _submission(user.id)
    repo.get_submission_by_id.return_value = submission
    s3.generate_presigned_upload_url.return_value = "https://presigned"
    s3.build_public_url.return_value = "https://public/object"
    service = UploadService(repository=repo, s3_service=s3, settings=settings)

    contexts = {
        "owner_document": ("passport.pdf", "application/pdf"),
        "property_media_video": ("tour.mp4", "video/mp4"),
        "property_document": ("title-deed.pdf", "application/pdf"),
    }
    for context, (name, content_type) in contexts.items():
        out = service.generate_presigned_upload(
            body=PresignedUploadRequest(
                submission_id=submission.id,
                context=context,  # type: ignore[arg-type]
                file_name=name,
                content_type=content_type,
                file_size=1024,
            ),
            user=user,
        )
        assert out.upload_url == "https://presigned"
        assert out.url == "https://public/object"
        assert out.requires_watermark_finalize is False
        assert out.upload_completed is False


def test_json_presigned_property_media_image_returns_watermark_finalize() -> None:
    user = SimpleNamespace(id=uuid.uuid4())
    repo = MagicMock()
    s3 = MagicMock()
    submission = _submission(user.id)
    repo.get_submission_by_id.return_value = submission
    s3.generate_presigned_upload_url.return_value = "https://presigned-original"
    s3.build_public_url.side_effect = lambda key: f"https://public/{key}"
    service = UploadService(repository=repo, s3_service=s3, settings=_settings())

    out = service.generate_presigned_upload(
        body=PresignedUploadRequest(
            submission_id=submission.id,
            context="property_media_image",
            file_name="download (3).jpeg",
            content_type="image/jpeg",
            file_size=7166,
        ),
        user=user,
    )
    assert out.upload_url == "https://presigned-original"
    assert out.requires_watermark_finalize is True
    assert out.upload_completed is False
    assert out.original_url is not None
    assert "/original/" in out.original_url
    assert "/watermarked/" in out.url
    key = s3.generate_presigned_upload_url.call_args.kwargs["key"]
    assert "/original/" in key
    assert "download" in key


def test_extension_allowed_with_or_without_dot_in_env() -> None:
    """Env may list jpg or .jpg; Path.suffix is always dotted."""
    user = SimpleNamespace(id=uuid.uuid4())
    repo = MagicMock()
    s3 = MagicMock()
    settings = SimpleNamespace(
        aws_s3_presigned_expiry=900,
        allowed_property_image_extensions=["jpg", "jpeg"],  # no leading dots
        allowed_property_video_extensions=[".mp4"],
        allowed_property_document_extensions=["pdf"],
        property_image_max_size_mb=20,
        property_video_max_size_mb=100,
        property_document_max_size_mb=20,
    )
    submission = _submission(user.id)
    repo.get_submission_by_id.return_value = submission
    s3.generate_presigned_upload_url.return_value = "https://presigned"
    s3.build_public_url.return_value = "https://public/a.jpg"
    service = UploadService(repository=repo, s3_service=s3, settings=settings)

    out = service.generate_presigned_upload(
        body=PresignedUploadRequest(
            submission_id=submission.id,
            context="property_media_video",
            file_name="tour.mp4",
            content_type="video/mp4",
            file_size=None,
        ),
        user=user,
    )
    assert out.upload_url == "https://presigned"


def test_invalid_extension_rejected() -> None:
    user = SimpleNamespace(id=uuid.uuid4())
    repo = MagicMock()
    s3 = MagicMock()
    submission = _submission(user.id)
    repo.get_submission_by_id.return_value = submission
    service = UploadService(repository=repo, s3_service=s3, settings=_settings())

    with pytest.raises(HTTPException) as exc_info:
        service.generate_presigned_upload(
            body=PresignedUploadRequest(
                submission_id=submission.id,
                context="property_media_image",
                file_name="malware.exe",
                content_type="image/jpeg",
                file_size=100,
            ),
            user=user,
        )
    assert exc_info.value.status_code == 400
    detail = str(exc_info.value.detail)
    assert "property_media_image" in detail
    assert ".jpg" in detail or ".jpeg" in detail or ".png" in detail


def test_rejects_invalid_content_type_for_context() -> None:
    user = SimpleNamespace(id=uuid.uuid4())
    repo = MagicMock()
    s3 = MagicMock()
    submission = _submission(user.id)
    repo.get_submission_by_id.return_value = submission
    service = UploadService(repository=repo, s3_service=s3, settings=_settings())

    with pytest.raises(HTTPException) as exc_info:
        service.generate_presigned_upload(
            body=PresignedUploadRequest(
                submission_id=submission.id,
                context="property_media_video",
                file_name="tour.mp4",
                content_type="image/png",
                file_size=1024,
            ),
            user=user,
        )
    assert exc_info.value.status_code == 400


def test_rejects_file_size_above_limit() -> None:
    user = SimpleNamespace(id=uuid.uuid4())
    repo = MagicMock()
    s3 = MagicMock()
    submission = _submission(user.id)
    repo.get_submission_by_id.return_value = submission
    service = UploadService(repository=repo, s3_service=s3, settings=_settings())

    with pytest.raises(HTTPException) as exc_info:
        service.generate_presigned_upload(
            body=PresignedUploadRequest(
                submission_id=submission.id,
                context="property_document",
                file_name="doc.pdf",
                content_type="application/pdf",
                file_size=(21 * 1024 * 1024),
            ),
            user=user,
        )
    assert exc_info.value.status_code == 400


def test_json_presigned_property_media_image_accepts_draft_client_id() -> None:
    user = SimpleNamespace(id=uuid.uuid4())
    repo = MagicMock()
    s3 = MagicMock()
    client_id = uuid.uuid4()
    s3.generate_presigned_upload_url.return_value = "https://presigned"
    s3.build_public_url.return_value = "https://public/object"
    service = UploadService(repository=repo, s3_service=s3, settings=_settings())

    out = service.generate_presigned_upload(
        body=PresignedUploadRequest(
            draft_client_id=client_id,
            context="property_media_image",
            file_name="front.jpg",
            content_type="image/jpeg",
            file_size=1024,
        ),
        user=user,
    )
    assert not repo.get_submission_by_id.called
    assert out.requires_watermark_finalize is True
    key = s3.generate_presigned_upload_url.call_args.kwargs["key"]
    assert str(client_id) in key


def test_presigned_uses_draft_client_id_without_submission_row() -> None:
    user = SimpleNamespace(id=uuid.uuid4())
    repo = MagicMock()
    s3 = MagicMock()
    client_id = uuid.uuid4()
    s3.generate_presigned_upload_url.return_value = "https://presigned"
    s3.build_public_url.return_value = "https://public/object"
    service = UploadService(repository=repo, s3_service=s3, settings=_settings())

    out = service.generate_presigned_upload(
        body=PresignedUploadRequest(
            draft_client_id=client_id,
            context="property_media_video",
            file_name="tour.mp4",
            content_type="video/mp4",
            file_size=50,
        ),
        user=user,
    )
    assert not repo.get_submission_by_id.called
    key = s3.generate_presigned_upload_url.call_args.kwargs["key"]
    assert str(client_id) in key
    assert "drafts/property-submissions" in key
    assert out.upload_url == "https://presigned"


def test_submission_id_path_still_loads_submission() -> None:
    user = SimpleNamespace(id=uuid.uuid4())
    repo = MagicMock()
    s3 = MagicMock()
    submission = _submission(user.id)
    repo.get_submission_by_id.return_value = submission
    s3.generate_presigned_upload_url.return_value = "x"
    s3.build_public_url.return_value = "y"
    service = UploadService(repository=repo, s3_service=s3, settings=_settings())
    out = service.generate_presigned_upload(
        body=PresignedUploadRequest(
            submission_id=submission.id,
            context="property_media_video",
            file_name="tour.mp4",
            content_type="video/mp4",
        ),
        user=user,
    )
    repo.get_submission_by_id.assert_called_once()
    assert out.upload_url


def test_presigned_blocks_deleted_submission_id() -> None:
    user = SimpleNamespace(id=uuid.uuid4())
    repo = MagicMock()
    s3 = MagicMock()
    submission = _submission(user.id)
    submission.deleted_at = object()
    repo.get_submission_by_id.return_value = submission
    service = UploadService(repository=repo, s3_service=s3, settings=_settings())
    with pytest.raises(HTTPException) as exc_info:
        service.generate_presigned_upload(
            body=PresignedUploadRequest(
                submission_id=submission.id,
                context="property_media_image",
                file_name="a.jpg",
                content_type="image/jpeg",
            ),
            user=user,
        )
    assert exc_info.value.status_code == 404

