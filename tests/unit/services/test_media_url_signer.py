"""Tests for MediaUrlSigner (presigned GET for responses)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.schemas.user import UserResponse
from app.services.media_url_signer import MediaUrlSigner
import uuid
from datetime import datetime, timezone


def test_sign_user_response_rewrites_s3_url() -> None:
    s3 = MagicMock()
    s3.generate_presigned_get_url.return_value = "https://signed-get"
    settings = MagicMock()
    settings.aws_s3_bucket = "b"
    settings.aws_region = "us-west-2"
    settings.aws_s3_public_base_url = None
    settings.aws_s3_endpoint_url = None
    settings.aws_s3_presigned_get_expiry_seconds = 3600

    signer = MediaUrlSigner(s3_service=s3, settings=settings)
    uid = uuid.uuid4()
    user = UserResponse(
        id=uid,
        email="a@b.com",
        full_name="A",
        phone_number="+12025551234",
        is_active=True,
        is_email_verified=True,
        is_phone_verified=False,
        profile_picture_url=f"https://b.s3.us-west-2.amazonaws.com/users/profile/{uid}/profile_pic/x.png",
        roles=[],
        created_at=datetime.now(timezone.utc),
        requires_password_set=False,
    )
    signer.apply_user_response(user)
    assert user.profile_picture_url == "https://signed-get"
    s3.generate_presigned_get_url.assert_called_once()


def test_sign_user_response_passes_external() -> None:
    s3 = MagicMock()
    settings = MagicMock()
    settings.aws_s3_bucket = "b"
    settings.aws_region = "us-west-2"
    settings.aws_s3_public_base_url = None
    settings.aws_s3_endpoint_url = None
    settings.aws_s3_presigned_get_expiry_seconds = 3600

    signer = MediaUrlSigner(s3_service=s3, settings=settings)
    uid = uuid.uuid4()
    user = UserResponse(
        id=uid,
        email="a@b.com",
        full_name="A",
        phone_number="+12025551234",
        is_active=True,
        is_email_verified=True,
        is_phone_verified=False,
        profile_picture_url="https://cdn.example.com/face.png",
        roles=[],
        created_at=datetime.now(timezone.utc),
        requires_password_set=False,
    )
    signer.apply_user_response(user)
    assert user.profile_picture_url == "https://cdn.example.com/face.png"
    s3.generate_presigned_get_url.assert_not_called()
