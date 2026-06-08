"""Tests for MediaUrlSigner (presigned GET for responses)."""

from __future__ import annotations

from unittest.mock import MagicMock

import uuid
from datetime import datetime, timezone

from app.schemas.agency import AgencyLogoUploadResponse, AgencyResponse
from app.schemas.user import UserResponse
from app.services.media_url_signer import MediaUrlSigner


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


def test_sign_agency_response_rewrites_legal_document() -> None:
    s3 = MagicMock()
    s3.generate_presigned_get_url.return_value = "https://signed-legal-get"
    settings = MagicMock()
    settings.aws_s3_bucket = "b"
    settings.aws_region = "us-west-2"
    settings.aws_s3_public_base_url = None
    settings.aws_s3_endpoint_url = None
    settings.aws_s3_presigned_get_expiry_seconds = 3600

    signer = MediaUrlSigner(s3_service=s3, settings=settings)
    agency_id = uuid.uuid4()
    agency = AgencyResponse(
        id=agency_id,
        agency_name="A",
        agency_trade_name="A",
        legal_document_s3_link=(
            f"https://b.s3.us-west-2.amazonaws.com/{agency_id}/profile_doc/doc.pdf"
        ),
        email="agency@example.com",
        phone="+12025551234",
        is_active=True,
        is_verified=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    signer.apply_agency_response(agency)
    assert agency.legal_document_s3_link == "https://signed-legal-get"
    s3.generate_presigned_get_url.assert_called_once()


def test_sign_agency_response_skips_pending_placeholder() -> None:
    s3 = MagicMock()
    settings = MagicMock()
    settings.aws_s3_bucket = "b"
    settings.aws_region = "us-west-2"
    settings.aws_s3_public_base_url = None
    settings.aws_s3_endpoint_url = None
    settings.aws_s3_presigned_get_expiry_seconds = 3600

    signer = MediaUrlSigner(s3_service=s3, settings=settings)
    agency_id = uuid.uuid4()
    agency = AgencyResponse(
        id=agency_id,
        agency_name="A",
        agency_trade_name="A",
        legal_document_s3_link="__pending_legal_document_upload__",
        email="agency@example.com",
        phone="+12025551234",
        is_active=True,
        is_verified=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    signer.apply_agency_response(agency)
    assert agency.legal_document_s3_link == "__pending_legal_document_upload__"
    s3.generate_presigned_get_url.assert_not_called()


def test_sign_agency_logo_upload_response() -> None:
    s3 = MagicMock()
    s3.generate_presigned_get_url.return_value = "https://signed-logo-get"
    settings = MagicMock()
    settings.aws_s3_bucket = "b"
    settings.aws_region = "us-west-2"
    settings.aws_s3_public_base_url = None
    settings.aws_s3_endpoint_url = None
    settings.aws_s3_presigned_get_expiry_seconds = 3600

    signer = MediaUrlSigner(s3_service=s3, settings=settings)
    agency_id = uuid.uuid4()
    data = AgencyLogoUploadResponse(
        logo_url=f"https://b.s3.us-west-2.amazonaws.com/{agency_id}/profile_doc/logo/logo.png",
        upload_url="https://put-url",
        expires_in=3600,
    )
    signer.apply_agency_logo_upload_response(data)
    assert data.logo_url == "https://signed-logo-get"
    assert data.upload_url == "https://put-url"
