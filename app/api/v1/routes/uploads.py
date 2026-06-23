from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import DBSessionDep, RequestContext, require_authenticated_user
from app.schemas.uploads import PresignedUploadRequest
from app.utils.api_response import success_response
from app.utils.status_codes import STATUS_BAD_REQUEST

router = APIRouter()
AuthenticatedContext = Annotated[RequestContext, Depends(require_authenticated_user)]


@router.post("/presigned-url")
def create_presigned_upload_url(payload: PresignedUploadRequest, context: AuthenticatedContext, db: DBSessionDep) -> dict:
    if payload.context == "owner_document" and not payload.draft_client_id:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="draft_client_id is required for owner documents")
    if payload.context in {"property_media_image", "property_document"} and not payload.submission_id:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="submission_id is required for property uploads")

    safe_file_name = PurePosixPath(payload.file_name).name
    owner = payload.draft_client_id or payload.submission_id or str(context.user_id)
    object_key = f"{payload.context}/{owner}/{uuid4()}-{safe_file_name}"
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

