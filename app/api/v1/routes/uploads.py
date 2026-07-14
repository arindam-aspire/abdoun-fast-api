from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import DBSessionDep, RequestContext, require_authenticated_user
from app.core.config import get_settings
from app.schemas.uploads import PresignedUploadRequest, ReadableUrlRequest
from app.services.media_urls import (
    canonicalize_media_url,
    generate_presigned_put_url,
    resolve_readable_media_url,
)
from app.services.media_urls import canonicalize_media_url, resolve_readable_media_url
from app.utils.api_response import success_response
from app.utils.status_codes import STATUS_BAD_REQUEST, STATUS_INTERNAL_SERVER_ERROR

router = APIRouter()

AuthenticatedContext = Annotated[RequestContext, Depends(require_authenticated_user)]


def _s3_client(*, region: str):
    """Build an S3 client with regional endpoint for stable SigV4 presigns."""
    return boto3.client(
        "s3",
        region_name=region,
        endpoint_url=f"https://s3.{region}.amazonaws.com",
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "virtual"},
        ),
    )


def _s3_object_url(bucket: str, region: str, object_key: str) -> str:
    encoded_key = quote(object_key, safe="/")
    return f"https://{bucket}.s3.{region}.amazonaws.com/{encoded_key}"


@router.post("/presigned-url")
def create_presigned_upload_url(payload: PresignedUploadRequest, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    if payload.context == "owner_document" and not payload.draft_client_id:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="draft_client_id is required for owner documents")
    if payload.context in {"property_media_image", "property_document"} and not (payload.submission_id or payload.draft_client_id):
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="submission_id or draft_client_id is required for property uploads")
    if payload.context == "agent_identity_document":
        from app.schemas.agents import ALLOWED_IDENTITY_EXTENSIONS, IDENTITY_DOCUMENT_MAX_BYTES

        lowered = payload.file_name.strip().lower()
        if not any(lowered.endswith(ext) for ext in ALLOWED_IDENTITY_EXTENSIONS):
            raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="identity document must be PDF, JPG, or PNG")
        if payload.file_size > IDENTITY_DOCUMENT_MAX_BYTES:
            raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="identity document must be 5 MB or smaller")

    content_type = (payload.content_type or "").strip()
    if not content_type:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="content_type is required")

    safe_file_name = PurePosixPath(payload.file_name).name
    owner = payload.draft_client_id or payload.submission_id or str(context.user_id)
    object_key = f"{payload.context}/{owner}/{uuid4()}-{safe_file_name}"

    settings = get_settings()
    bucket = (settings.aws_s3_bucket or "").strip().strip("\"'")
    presigned = generate_presigned_put_url(object_key)
    if bucket and not presigned:
        raise HTTPException(
            status_code=STATUS_INTERNAL_SERVER_ERROR,
            detail="Could not generate upload URL",
        )
    if presigned:
        # Private bucket: file_url is for storage only (AccessDenied if opened raw).
        # readable_url / signed_read_url are short-lived GET signatures for preview.
        return success_response(
            {
                "upload_url": presigned["upload_url"],
                "object_key": presigned["object_key"],
                "file_url": presigned["file_url"],
                "readable_url": presigned["readable_url"],
                "signed_read_url": presigned["signed_read_url"],
            },
            "Upload URL generated",
            meta={
                "mode": "s3",
                "content_type": content_type,
                "file_size": payload.file_size,
                "expires_in": presigned["expires_in"],
                "readable_expires_in": presigned["readable_expires_in"],
            },
        )

    dev_url = f"dev://uploads/{object_key}"
    return success_response(
        {
            "upload_url": dev_url,
            "object_key": object_key,
            "file_url": dev_url,
            "readable_url": dev_url,
            "signed_read_url": dev_url,
        },
        "Dev upload URL generated",
        meta={
            "mode": "log",
            "content_type": content_type,
            "file_size": payload.file_size,
        },
    )


@router.post("/readable-url")
def create_readable_media_url(payload: ReadableUrlRequest, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    """Exchange a stored S3 file_url (or expired upload URL) for a short-lived GET URL."""
    file_url = (payload.file_url or "").strip()
    if not file_url:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="file_url is required")

    canonical = canonicalize_media_url(file_url) or file_url
    readable = resolve_readable_media_url(canonical)
    if not readable:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Could not resolve media URL")

    settings = get_settings()
    return success_response(
        {
            "file_url": canonical,
            "readable_url": readable,
            "signed_read_url": readable,
        },
        "Readable URL generated",
        meta={"expires_in": settings.media_url_presign_expires_seconds},
    )
