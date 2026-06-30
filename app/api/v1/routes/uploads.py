from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated
from urllib.parse import quote
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import DBSessionDep, RequestContext, require_authenticated_user
from app.core.config import get_settings
from app.schemas.uploads import PresignedUploadRequest
from app.utils.api_response import success_response
from app.utils.status_codes import STATUS_BAD_REQUEST, STATUS_INTERNAL_SERVER_ERROR

router = APIRouter()
AuthenticatedContext = Annotated[RequestContext, Depends(require_authenticated_user)]


def _s3_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        config=Config(signature_version="s3v4"),
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

    safe_file_name = PurePosixPath(payload.file_name).name
    owner = payload.draft_client_id or payload.submission_id or str(context.user_id)
    object_key = f"{payload.context}/{owner}/{uuid4()}-{safe_file_name}"

    settings = get_settings()
    bucket = settings.aws_s3_bucket
    if bucket:
        try:
            upload_url = _s3_client().generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": bucket,
                    "Key": object_key,
                    "ContentType": payload.content_type,
                },
                ExpiresIn=settings.media_upload_presign_expires_seconds,
            )
        except (BotoCoreError, ClientError) as exc:
            raise HTTPException(
                status_code=STATUS_INTERNAL_SERVER_ERROR,
                detail="Could not generate upload URL",
            ) from exc

        return success_response(
            {
                "upload_url": upload_url,
                "file_url": _s3_object_url(bucket, settings.aws_region, object_key),
            },
            "Upload URL generated",
            meta={
                "mode": "s3",
                "content_type": payload.content_type,
                "file_size": payload.file_size,
                "expires_in": settings.media_upload_presign_expires_seconds,
            },
        )

    dev_url = f"dev://uploads/{object_key}"
    return success_response(
        {
            "upload_url": dev_url,
            "file_url": dev_url,
        },
        "Dev upload URL generated",
        meta={
            "mode": "log",
            "content_type": payload.content_type,
            "file_size": payload.file_size,
        },
    )
