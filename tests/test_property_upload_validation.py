from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.deps import RequestContext
from app.api.v1.routes import uploads
from app.schemas.uploads import PresignedUploadRequest


@pytest.fixture(autouse=True)
def use_dev_uploads(monkeypatch) -> None:
    monkeypatch.setattr(uploads, "get_settings", lambda: SimpleNamespace(aws_s3_bucket=""))
    monkeypatch.setattr(uploads, "generate_presigned_put_url", lambda object_key: None)


@pytest.mark.parametrize(
    ("context", "file_name", "content_type"),
    [
        ("property_media_image", "photo.jpg", "image/jpeg"),
        ("property_media_image", "photo.JPEG", "image/jpeg"),
        ("property_media_image", "photo.png", "image/png"),
        ("property_media_image", "photo.webp", "image/webp"),
        ("property_media_image", "photo.gif", "image/gif"),
        ("property_media_image", "tour.mp4", "video/mp4"),
        ("property_media_image", "tour.mov", "video/quicktime"),
        ("property_document", "terms.doc", "application/msword"),
        (
            "property_document",
            "terms.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("property_document", "terms.pdf", "application/pdf; charset=binary"),
    ],
)
def test_property_upload_accepts_supported_extension_and_mime(
    context: str,
    file_name: str,
    content_type: str,
) -> None:
    payload = PresignedUploadRequest(
        context=context,
        file_name=file_name,
        content_type=content_type,
        file_size=100,
        draft_client_id="draft-1",
    )

    response = uploads.create_presigned_upload_url(
        payload,
        RequestContext(locale="en", user_id=uuid4()),
        None,
    )

    assert response["data"]["object_key"].startswith(f"{context}/draft-1/")
    assert response["meta"]["content_type"] == content_type


@pytest.mark.parametrize(
    ("context", "file_name", "content_type"),
    [
        ("property_media_image", "photo.svg", "image/svg+xml"),
        ("property_media_image", "photo.jpg", "video/mp4"),
        ("property_media_image", "tour.mp4", "application/octet-stream"),
        ("property_document", "sheet.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("property_document", "terms.pdf", "application/msword"),
        ("property_document", "terms.docx", "application/octet-stream"),
    ],
)
def test_property_upload_rejects_unsupported_or_mismatched_type(
    context: str,
    file_name: str,
    content_type: str,
) -> None:
    payload = PresignedUploadRequest(
        context=context,
        file_name=file_name,
        content_type=content_type,
        file_size=100,
        draft_client_id="draft-1",
    )

    with pytest.raises(HTTPException) as exc_info:
        uploads.create_presigned_upload_url(
            payload,
            RequestContext(locale="en", user_id=uuid4()),
            None,
        )

    assert exc_info.value.status_code == 400
