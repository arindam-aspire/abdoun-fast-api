"""Upload helper endpoints for presigned URL workflow and watermarked property images."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import ValidationError
from fastapi.responses import JSONResponse

from app.api.v1.deps.security import get_current_user
from app.api.v1.deps.uploads import (
    get_property_image_upload_service,
    get_upload_service,
)
from app.core.config import get_settings
from app.exceptions.property_image_upload import PropertyImageUploadError
from app.models.user import User
from app.schemas.uploads import (
    PresignedUploadData,
    PresignedUploadRequest,
    PropertyImageFinalizeRequest,
    PropertyImageUploadData,
)
from app.services.property_image_upload_service import PropertyImageUploadService
from app.services.upload_service import UploadService
from app.utils.multipart_limits import parse_property_image_form
from app.utils.responses import StandardResponse, create_success_response
from app.utils.status_codes import HTTPStatus

router = APIRouter()
logger = logging.getLogger(__name__)


def _property_image_error_response(exc: PropertyImageUploadError) -> JSONResponse:
    content: dict[str, object] = {"success": False, "message": exc.message}
    if exc.detail is not None:
        content["detail"] = exc.detail
    return JSONResponse(status_code=exc.status_code, content=content)


def _parse_form_uuid(value: str | None) -> uuid.UUID | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return uuid.UUID(str(value).strip())


@router.post("/presigned-url", response_model=StandardResponse[PresignedUploadData])
async def get_presigned_upload_url(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    upload_service: Annotated[UploadService, Depends(get_upload_service)],
    image_service: Annotated[PropertyImageUploadService, Depends(get_property_image_upload_service)],
):
    """Presigned URL for videos/documents (JSON). Property images: multipart with ``file`` — watermark + S3 in one call.

    **Property images** — either:

    - ``application/json``: presigned PUT to ``upload_url``, then
      ``POST /uploads/property-images/finalize`` when ``requires_watermark_finalize`` is true; or
    - ``multipart/form-data`` on this path: ``file``, ``context=property_media_image``,
      ``submission_id`` *or* ``draft_client_id`` (server watermarks in one request).

    **Videos/documents** — ``application/json``; client PUTs to ``upload_url`` after presign.
    """
    content_type = (request.headers.get("content-type") or "").lower()

    if "multipart/form-data" in content_type:
        return await _presigned_url_multipart(
            request=request,
            current_user=current_user,
            upload_service=upload_service,
            image_service=image_service,
        )

    try:
        raw = await request.json()
    except Exception as exc:
        logger.warning("[presigned-url] invalid JSON body user_id=%s", current_user.id)
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid JSON body") from exc

    try:
        body = PresignedUploadRequest.model_validate(raw)
    except ValidationError as exc:
        logger.warning(
            "[presigned-url] validation failed user_id=%s body=%s errors=%s",
            current_user.id,
            raw,
            exc.errors(),
        )
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=exc.errors()) from exc

    logger.info(
        "[presigned-url] json user_id=%s context=%s submission_id=%s draft_client_id=%s file_name=%s content_type=%s file_size=%s",
        current_user.id,
        body.context,
        body.submission_id,
        body.draft_client_id,
        body.file_name,
        body.content_type,
        body.file_size,
    )

    try:
        data = upload_service.generate_presigned_upload(body=body, user=current_user)
    except HTTPException:
        logger.warning(
            "[presigned-url] rejected user_id=%s context=%s submission_id=%s draft_client_id=%s",
            current_user.id,
            body.context,
            body.submission_id,
            body.draft_client_id,
        )
        raise
    except Exception:
        logger.exception(
            "[presigned-url] unexpected error user_id=%s context=%s",
            current_user.id,
            body.context,
        )
        raise
    return create_success_response(data=data, message=None)


async def _presigned_url_multipart(
    *,
    request: Request,
    current_user: User,
    upload_service: UploadService,
    image_service: PropertyImageUploadService,
) -> StandardResponse[PresignedUploadData]:
    form = await parse_property_image_form(request)
    context = form.get("context")
    if context != "property_media_image":
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Multipart on /uploads/presigned-url is only supported for context=property_media_image",
        )

    upload = form.get("file")
    if upload is None or not hasattr(upload, "read"):
        raise PropertyImageUploadError(
            status_code=HTTPStatus.BAD_REQUEST,
            message="Invalid file",
            detail="file is required in multipart form",
        )

    submission_id = _parse_form_uuid(form.get("submission_id"))  # type: ignore[arg-type]
    draft_client_id = _parse_form_uuid(form.get("draft_client_id"))  # type: ignore[arg-type]
    file_name = form.get("file_name")
    content_type_field = form.get("content_type")
    file_size_raw = form.get("file_size")

    file_bytes = await upload.read()  # type: ignore[union-attr]
    filename = getattr(upload, "filename", None) or (str(file_name) if file_name else None)
    mime = getattr(upload, "content_type", None) or (
        str(content_type_field) if content_type_field else None
    )

    logger.info(
        "[presigned-url] property image multipart user_id=%s submission_id=%s draft_client_id=%s file=%s",
        current_user.id,
        submission_id,
        draft_client_id,
        filename,
    )

    try:
        uploaded = image_service.upload_property_image(
            user=current_user,
            file_bytes=file_bytes,
            filename=filename,
            content_type=mime,
            submission_id=submission_id,
            draft_client_id=draft_client_id,
        )
    except PropertyImageUploadError as exc:
        return _property_image_error_response(exc)  # type: ignore[return-value]

    expiry = get_settings().aws_s3_presigned_expiry
    data = PresignedUploadData(
        upload_url=uploaded.url,
        url=uploaded.url,
        original_url=uploaded.original_url,
        expires_in=expiry,
        upload_completed=True,
        requires_watermark_finalize=False,
    )
    logger.info(
        "[presigned-url] property image done file_name=%s url=%s (no client PUT needed)",
        uploaded.file_name,
        uploaded.url,
    )
    return create_success_response(data=data, message=None)


@router.post("/property-images", response_model=StandardResponse[PropertyImageUploadData])
async def upload_property_image(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[PropertyImageUploadService, Depends(get_property_image_upload_service)],
    file: Annotated[UploadFile | None, File()] = None,
    submission_id: Annotated[uuid.UUID | None, Form()] = None,
    draft_client_id: Annotated[uuid.UUID | None, Form()] = None,
):
    """Alias of multipart presigned-url for property images (prefer POST /presigned-url)."""
    if file is None:
        raise PropertyImageUploadError(
            status_code=HTTPStatus.BAD_REQUEST,
            message="Invalid file",
            detail="file is required",
        )
    try:
        file_bytes = await file.read()
        data = service.upload_property_image(
            user=current_user,
            file_bytes=file_bytes,
            filename=file.filename,
            content_type=file.content_type,
            submission_id=submission_id,
            draft_client_id=draft_client_id,
        )
    except PropertyImageUploadError as exc:
        return _property_image_error_response(exc)  # type: ignore[return-value]
    return create_success_response(
        data=data,
        message="Property image uploaded successfully",
    )


@router.post("/property-images/finalize", response_model=StandardResponse[PropertyImageUploadData])
def finalize_presigned_property_image(
    body: PropertyImageFinalizeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[PropertyImageUploadService, Depends(get_property_image_upload_service)],
):
    """Manual retry only (normal flow uses multipart presigned-url)."""
    try:
        data = service.finalize_presigned_property_image(
            user=current_user,
            filename=body.file_name,
            submission_id=body.submission_id,
            draft_client_id=body.draft_client_id,
        )
    except PropertyImageUploadError as exc:
        return _property_image_error_response(exc)  # type: ignore[return-value]
    return create_success_response(
        data=data,
        message="Property image watermarked successfully",
    )
