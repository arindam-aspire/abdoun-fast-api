"""Tests for agency logo upload service (S3 path, replace, presigned GET)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.schemas.agency import AgencyLogoUploadRequest
from app.services.agency_logo_upload_service import AgencyLogoUploadService


def _service(*, agency=None, s3=None) -> tuple[AgencyLogoUploadService, MagicMock, MagicMock]:
    repo = MagicMock()
    repo.get_by_id.return_value = agency
    s3 = s3 or MagicMock()
    s3.build_public_url.side_effect = lambda key: f"https://bucket.s3.us-west-2.amazonaws.com/{key}"
    s3.generate_presigned_upload_url.return_value = "https://presigned-put"
    s3.generate_presigned_get_url.return_value = "https://presigned-get"
    s3.object_exists.return_value = True

    settings = MagicMock()
    settings.aws_s3_bucket = "bucket"
    settings.aws_region = "us-west-2"
    settings.aws_s3_public_base_url = None
    settings.aws_s3_endpoint_url = None
    settings.aws_s3_presigned_expiry = 3600
    settings.aws_s3_presigned_get_expiry_seconds = 3600
    settings.allowed_property_image_extensions = [".png", ".jpg", ".jpeg", ".webp"]
    settings.property_image_max_size_mb = 10

    return AgencyLogoUploadService(repo, s3, settings=settings), repo, s3


def _user(*, agency_id: uuid.UUID | None = None) -> MagicMock:
    user = MagicMock()
    user.agency_id = agency_id
    role = MagicMock()
    role.name = "admin"
    user.roles = [role]
    return user


def test_initiate_upload_uses_profile_doc_logo_path_and_deletes_old() -> None:
    agency_id = uuid.uuid4()
    agency = MagicMock()
    agency.id = agency_id
    agency.logo_url = f"https://bucket.s3.us-west-2.amazonaws.com/{agency_id}/profile_doc/logo/old.png"

    service, repo, s3 = _service(agency=agency)
    body = AgencyLogoUploadRequest(
        file_name="new.png",
        content_type="image/png",
        file_size=100,
    )

    result = service.initiate_upload(
        agency_id=agency_id,
        current_user=_user(agency_id=agency_id),
        body=body,
    )

    expected_key = f"{agency_id}/profile_doc/logo/new.png"
    s3.delete_object.assert_called_once_with(key=f"{agency_id}/profile_doc/logo/old.png")
    s3.generate_presigned_upload_url.assert_called_once()
    assert s3.generate_presigned_upload_url.call_args.kwargs["key"] == expected_key
    assert agency.logo_url.endswith(expected_key)
    assert result.upload_url == "https://presigned-put"
    repo.commit.assert_called()


def test_get_logo_returns_presigned_get() -> None:
    agency_id = uuid.uuid4()
    agency = MagicMock()
    agency.logo_url = f"https://bucket.s3.us-west-2.amazonaws.com/{agency_id}/profile_doc/logo/logo.png"

    service, _repo, s3 = _service(agency=agency)
    result = service.get_logo(agency_id=agency_id, current_user=_user(agency_id=agency_id))

    assert result.logo_url == "https://presigned-get"
    assert result.expires_in == 3600
    s3.generate_presigned_get_url.assert_called_once_with(
        key=f"{agency_id}/profile_doc/logo/logo.png",
        expires_in=3600,
    )


def test_delete_logo_clears_db_and_deletes_s3() -> None:
    agency_id = uuid.uuid4()
    agency = MagicMock()
    agency.logo_url = f"https://bucket.s3.us-west-2.amazonaws.com/{agency_id}/profile_doc/logo/logo.png"

    service, repo, s3 = _service(agency=agency)
    assert service.delete_logo(agency_id=agency_id, current_user=_user(agency_id=agency_id)) is True
    s3.delete_object.assert_called_once_with(key=f"{agency_id}/profile_doc/logo/logo.png")
    assert agency.logo_url is None
    repo.commit.assert_called()


def test_delete_logo_not_found_when_empty() -> None:
    agency_id = uuid.uuid4()
    agency = MagicMock()
    agency.logo_url = None

    service, _, _ = _service(agency=agency)
    with pytest.raises(HTTPException) as exc:
        service.delete_logo(agency_id=agency_id, current_user=_user(agency_id=agency_id))
    assert exc.value.status_code == 404


def test_get_logo_not_found_when_empty() -> None:
    agency_id = uuid.uuid4()
    agency = MagicMock()
    agency.logo_url = None

    service, _, _ = _service(agency=agency)
    with pytest.raises(HTTPException) as exc:
        service.get_logo(agency_id=agency_id, current_user=_user(agency_id=agency_id))
    assert exc.value.status_code == 404
