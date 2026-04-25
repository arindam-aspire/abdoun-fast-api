"""Unit tests for ProfilePictureUploadService (presigned profile picture flow)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.models.user import User
from app.schemas.user import ProfilePictureUploadRequest
from app.services.profile_picture_upload_service import ProfilePictureUploadService
from app.utils.status_codes import HTTPStatus


def _settings() -> MagicMock:
    s = MagicMock()
    s.allowed_property_image_extensions = [".jpg", ".jpeg", ".png", ".webp"]
    s.property_image_max_size_mb = 20
    s.aws_s3_bucket = "test-bucket"
    s.aws_s3_presigned_expiry = 900
    s.aws_region = "us-east-1"
    return s


def _user() -> User:
    u = User(
        email="u@example.com",
        full_name="U",
        phone_number="+12025551234",
        cognito_sub="sub-1",
    )
    u.id = uuid.uuid4()
    return u


def test_initiate_upload_success() -> None:
    repo = MagicMock()
    s3 = MagicMock()
    s3.build_public_url.return_value = "https://test-bucket.s3.us-east-1.amazonaws.com/users/profile/x/p.png"
    s3.generate_presigned_upload_url.return_value = "https://presigned-put"
    service = ProfilePictureUploadService(repository=repo, s3_service=s3, settings=_settings())
    user = _user()
    body = ProfilePictureUploadRequest(file_name="pic.png", content_type="image/png", file_size=1024)

    out = service.initiate_upload(user=user, body=body)

    assert out.profile_picture_url == s3.build_public_url.return_value
    assert out.upload_url == "https://presigned-put"
    assert out.expires_in == 900
    assert user.profile_picture_url == out.profile_picture_url
    repo.commit.assert_called_once()
    repo.refresh.assert_called_once_with(user)
    s3.generate_presigned_upload_url.assert_called_once()
    call_kw = s3.generate_presigned_upload_url.call_args.kwargs
    assert call_kw["content_type"] == "image/png"
    assert call_kw["key"].startswith(f"users/profile/{user.id}/profile_pic/")


def test_rejects_bad_extension() -> None:
    service = ProfilePictureUploadService(repository=MagicMock(), s3_service=MagicMock(), settings=_settings())
    with pytest.raises(HTTPException) as exc:
        service.initiate_upload(
            user=_user(),
            body=ProfilePictureUploadRequest(file_name="x.gif", content_type="image/gif", file_size=1),
        )
    assert exc.value.status_code == HTTPStatus.BAD_REQUEST


def test_rejects_oversized() -> None:
    service = ProfilePictureUploadService(repository=MagicMock(), s3_service=MagicMock(), settings=_settings())
    over = 21 * 1024 * 1024
    with pytest.raises(HTTPException) as exc:
        service.initiate_upload(
            user=_user(),
            body=ProfilePictureUploadRequest(file_name="x.png", content_type="image/png", file_size=over),
        )
    assert exc.value.status_code == HTTPStatus.BAD_REQUEST
    assert "20" in (exc.value.detail or "")


def test_rejects_non_image_content_type() -> None:
    service = ProfilePictureUploadService(repository=MagicMock(), s3_service=MagicMock(), settings=_settings())
    with pytest.raises(HTTPException) as exc:
        service.initiate_upload(
            user=_user(),
            body=ProfilePictureUploadRequest(file_name="x.png", content_type="application/octet-stream", file_size=1),
        )
    assert exc.value.status_code == HTTPStatus.BAD_REQUEST
