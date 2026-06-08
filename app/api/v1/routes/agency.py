"""Agency registration and management endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from pydantic import ValidationError

from app.api.v1.deps.agency import get_agency_profile_update_service, get_agency_service
from app.api.v1.deps.agency_logo_upload import get_agency_logo_upload_service
from app.api.v1.deps.media_urls import get_media_url_signer
from app.api.v1.deps.security import get_current_user
from app.core.limiter import limiter
from app.models.user import User
from app.schemas.agency import (
    AgencyDocumentUploadRequest,
    AgencyDocumentUploadResponse,
    AgencyLogoGetResponse,
    AgencyLogoUploadRequest,
    AgencyLogoUploadResponse,
    AgencyRegisterMultipartRequest,
    AgencyRegisterRequest,
    AgencyRegisterResponse,
    AgencyResponse,
    AgencyUpdateRequest,
    AgencyUpdateResult,
)
from app.schemas.user import (
    ProfileUpdateRequest,
    ProfileUpdateRequestResponse,
    ProfileUpdateVerifyRequest,
    ProfileUpdateVerifyResponse,
)
from app.services.agency_logo_upload_service import AgencyLogoUploadService
from app.services.agency_profile_update_service import AgencyProfileUpdateService
from app.services.agency_service import AgencyService
from app.services.media_url_signer import MediaUrlSigner
from app.utils.constants import SuccessMessages
from app.utils.constants import RateLimits
from app.utils.responses import StandardResponse, create_success_response
from app.utils.status_codes import HTTPStatus


router = APIRouter()

_LEGAL_DOCUMENT_FORM_KEYS = frozenset(
    {"legal_document", "legal_document_file", "legal_document_s3_link"}
)
_LOGO_FILE_FORM_KEYS = frozenset({"logo", "logo_file", "file", "image", "agency_logo"})


def _sign_agency_response(
    response: StandardResponse[AgencyResponse],
    media_signer: MediaUrlSigner,
) -> StandardResponse[AgencyResponse]:
    if response.data is not None:
        media_signer.apply_agency_response(response.data)
    return response


def _sign_agency_list_response(
    response: StandardResponse[list[AgencyResponse]],
    media_signer: MediaUrlSigner,
) -> StandardResponse[list[AgencyResponse]]:
    if response.data:
        for agency in response.data:
            media_signer.apply_agency_response(agency)
    return response


def _sign_agency_register_response(
    response: StandardResponse[AgencyRegisterResponse],
    media_signer: MediaUrlSigner,
) -> StandardResponse[AgencyRegisterResponse]:
    if response.data is None:
        return response
    media_signer.apply_agency_response(response.data.agency)
    if response.data.legal_document_upload is not None:
        media_signer.apply_agency_legal_document_upload_data(response.data.legal_document_upload)
    return response


def _sign_agency_document_upload_response(
    response: StandardResponse[AgencyDocumentUploadResponse],
    media_signer: MediaUrlSigner,
) -> StandardResponse[AgencyDocumentUploadResponse]:
    if response.data is not None:
        media_signer.apply_agency_document_upload_response(response.data)
    return response


def _sign_agency_update_response(
    response: StandardResponse[AgencyUpdateResult],
    media_signer: MediaUrlSigner,
) -> StandardResponse[AgencyUpdateResult]:
    if response.data is None:
        return response
    media_signer.apply_agency_response(response.data.agency)
    if response.data.legal_document_upload is not None:
        media_signer.apply_agency_legal_document_upload_data(response.data.legal_document_upload)
    return response


@router.post("/register", response_model=StandardResponse[AgencyRegisterResponse])
async def register_agency(
    request: Request,
    service: Annotated[AgencyService, Depends(get_agency_service)],
    media_signer: Annotated[MediaUrlSigner, Depends(get_media_url_signer)],
) -> StandardResponse[AgencyRegisterResponse]:
    """Register a new agency and its first agency admin user.

    Supports:
    - application/json with file_name, content_type, and optional file_size (presigned PUT upload)
    - multipart/form-data with a PDF file field named legal_document, legal_document_file, or legal_document_s3_link
    """
    content_type = (request.headers.get("content-type") or "").lower()
    try:
        if "multipart/form-data" in content_type:
            form = await request.form()
            upload = (
                form.get("legal_document")
                or form.get("legal_document_file")
                or form.get("legal_document_s3_link")
            )
            if not isinstance(upload, UploadFile) and not hasattr(upload, "read"):
                raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="legal_document PDF file is required")
            body = AgencyRegisterMultipartRequest.model_validate(
                {key: value for key, value in form.items() if key not in _LEGAL_DOCUMENT_FORM_KEYS}
            )
            file_bytes = await upload.read()
            response = service.register_with_legal_document(
                body=body,
                file_bytes=file_bytes,
                filename=upload.filename or "legal_document.pdf",
                content_type=upload.content_type,
            )
            return _sign_agency_register_response(response, media_signer)

        body = AgencyRegisterRequest.model_validate(await request.json())
        response = service.register(body)
        return _sign_agency_register_response(response, media_signer)
    except ValidationError as exc:
        raise HTTPException(status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=exc.errors()) from exc


@router.post("/upload-document", response_model=StandardResponse[AgencyDocumentUploadResponse])
def upload_agency_document(
    body: AgencyDocumentUploadRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AgencyService, Depends(get_agency_service)],
    media_signer: Annotated[MediaUrlSigner, Depends(get_media_url_signer)],
) -> StandardResponse[AgencyDocumentUploadResponse]:
    """Return a presigned S3 PUT URL and persist the canonical public URL on the agency (profile-picture pattern)."""
    response = service.create_document_upload(body=body, current_user=current_user)
    return _sign_agency_document_upload_response(response, media_signer)


@router.post(
    "/{agency_id}/logo",
    response_model=StandardResponse[AgencyLogoUploadResponse],
)
async def upload_agency_logo(
    request: Request,
    agency_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    upload_service: Annotated[AgencyLogoUploadService, Depends(get_agency_logo_upload_service)],
    media_signer: Annotated[MediaUrlSigner, Depends(get_media_url_signer)],
) -> StandardResponse[AgencyLogoUploadResponse]:
    """Agency logo: JSON presigned PUT (file_name, content_type) or multipart image file upload."""
    content_type = (request.headers.get("content-type") or "").lower()
    try:
        if "multipart/form-data" in content_type:
            form = await request.form()
            upload = None
            for key in _LOGO_FILE_FORM_KEYS:
                candidate = form.get(key)
                if candidate is not None and (isinstance(candidate, UploadFile) or hasattr(candidate, "read")):
                    upload = candidate
                    break
            if upload is not None:
                file_bytes = await upload.read()
                data = upload_service.upload_logo_file(
                    agency_id=agency_id,
                    current_user=current_user,
                    file_bytes=file_bytes,
                    filename=upload.filename or "logo.png",
                    content_type=upload.content_type,
                )
            else:
                body = AgencyLogoUploadRequest.model_validate(
                    {key: value for key, value in form.items() if key not in _LOGO_FILE_FORM_KEYS}
                )
                data = upload_service.initiate_upload(
                    agency_id=agency_id, current_user=current_user, body=body
                )
        else:
            body = AgencyLogoUploadRequest.model_validate(await request.json())
            data = upload_service.initiate_upload(
                agency_id=agency_id, current_user=current_user, body=body
            )
    except ValidationError as exc:
        raise HTTPException(status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=exc.errors()) from exc

    media_signer.apply_agency_logo_upload_response(data)
    return create_success_response(data=data, message=SuccessMessages.AGENCY_LOGO_UPLOADED)


@router.get(
    "/{agency_id}/logo",
    response_model=StandardResponse[AgencyLogoGetResponse],
)
def get_agency_logo(
    agency_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    upload_service: Annotated[AgencyLogoUploadService, Depends(get_agency_logo_upload_service)],
) -> StandardResponse[AgencyLogoGetResponse]:
    """Return a presigned GET URL for the agency logo (private bucket download)."""
    data = upload_service.get_logo(agency_id=agency_id, current_user=current_user)
    return create_success_response(data=data, message=None)


@router.delete(
    "/{agency_id}/logo",
    response_model=StandardResponse[bool],
)
def delete_agency_logo(
    agency_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    upload_service: Annotated[AgencyLogoUploadService, Depends(get_agency_logo_upload_service)],
) -> StandardResponse[bool]:
    """Delete agency logo from S3 and clear logo_url on the agency record."""
    upload_service.delete_logo(agency_id=agency_id, current_user=current_user)
    return create_success_response(data=True, message=SuccessMessages.AGENCY_LOGO_DELETED)


@router.get("/list", response_model=StandardResponse[list[AgencyResponse]])
def list_agencies(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AgencyService, Depends(get_agency_service)],
    media_signer: Annotated[MediaUrlSigner, Depends(get_media_url_signer)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> StandardResponse[list[AgencyResponse]]:
    """List agencies visible to the current user."""
    response = service.list_agencies(current_user=current_user, skip=skip, limit=limit)
    return _sign_agency_list_response(response, media_signer)


@router.patch(
    "/{agency_id}/profile/request",
    response_model=StandardResponse[ProfileUpdateRequestResponse],
)
@limiter.limit(RateLimits.PROFILE_UPDATE_REQUEST)
def request_agency_contact_update(
    request: Request,
    agency_id: UUID,
    body: ProfileUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    profile: Annotated[AgencyProfileUpdateService, Depends(get_agency_profile_update_service)],
):
    """Start OTP verification for agency email and/or phone (same flow as /auth/me/profile/request)."""
    data = profile.request_agency_contact_update(
        agency_id=agency_id, current_user=current_user, body=body
    )
    return create_success_response(data=data, message=data.message)


@router.post(
    "/{agency_id}/profile/verify",
    response_model=StandardResponse[ProfileUpdateVerifyResponse],
)
@limiter.limit(RateLimits.PROFILE_OTP_VERIFY)
def verify_agency_contact_update(
    request: Request,
    agency_id: UUID,
    body: ProfileUpdateVerifyRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    profile: Annotated[AgencyProfileUpdateService, Depends(get_agency_profile_update_service)],
):
    """Verify OTP(s) and apply agency email/phone changes."""
    data = profile.verify_agency_contact_update(
        agency_id=agency_id, current_user=current_user, body=body
    )
    return create_success_response(data=data, message=data.message)


@router.get("/{agency_id}", response_model=StandardResponse[AgencyResponse])
def get_agency(
    agency_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AgencyService, Depends(get_agency_service)],
    media_signer: Annotated[MediaUrlSigner, Depends(get_media_url_signer)],
) -> StandardResponse[AgencyResponse]:
    """Get agency details."""
    response = service.get_agency(agency_id=agency_id, current_user=current_user)
    return _sign_agency_response(response, media_signer)


@router.put("/{agency_id}", response_model=StandardResponse[AgencyUpdateResult])
async def update_agency(
    request: Request,
    agency_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AgencyService, Depends(get_agency_service)],
    media_signer: Annotated[MediaUrlSigner, Depends(get_media_url_signer)],
) -> StandardResponse[AgencyUpdateResult]:
    """Update agency fields, multipart legal PDF, or JSON presigned legal document upload."""
    content_type = (request.headers.get("content-type") or "").lower()
    try:
        if "multipart/form-data" in content_type:
            form = await request.form()
            upload = (
                form.get("legal_document")
                or form.get("legal_document_file")
                or form.get("legal_document_s3_link")
            )
            if not isinstance(upload, UploadFile) and not hasattr(upload, "read"):
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail="legal_document PDF file is required for multipart agency update",
                )
            body = AgencyUpdateRequest.model_validate(
                {key: value for key, value in form.items() if key not in _LEGAL_DOCUMENT_FORM_KEYS}
            )
            file_bytes = await upload.read()
            response = service.update_agency(
                agency_id=agency_id,
                body=body,
                current_user=current_user,
                legal_document_file=file_bytes,
                legal_document_filename=upload.filename or "legal_document.pdf",
                legal_document_content_type=upload.content_type,
            )
            return _sign_agency_update_response(response, media_signer)

        body = AgencyUpdateRequest.model_validate(await request.json())
        response = service.update_agency(agency_id=agency_id, body=body, current_user=current_user)
        return _sign_agency_update_response(response, media_signer)
    except ValidationError as exc:
        raise HTTPException(status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=exc.errors()) from exc


@router.delete("/{agency_id}", response_model=StandardResponse[bool])
def delete_agency(
    agency_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AgencyService, Depends(get_agency_service)],
) -> StandardResponse[bool]:
    """Delete an agency."""
    return service.delete_agency(agency_id=agency_id, current_user=current_user)
