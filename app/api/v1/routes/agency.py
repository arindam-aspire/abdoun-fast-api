"""Agency registration and management endpoints."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from pydantic import ValidationError

from app.api.v1.deps.agency import get_agency_service
from app.api.v1.deps.security import get_current_user
from app.models.user import User
from app.schemas.agency import (
    AgencyDocumentUploadRequest,
    AgencyDocumentUploadResponse,
    AgencyRegisterMultipartRequest,
    AgencyRegisterRequest,
    AgencyRegisterResponse,
    AgencyResponse,
    AgencyUpdateRequest,
)
from app.services.agency_service import AgencyService
from app.utils.responses import StandardResponse
from app.utils.status_codes import HTTPStatus


router = APIRouter()


@router.post("/register", response_model=StandardResponse[AgencyRegisterResponse])
async def register_agency(
    request: Request,
    service: Annotated[AgencyService, Depends(get_agency_service)],
) -> StandardResponse[AgencyRegisterResponse]:
    """Register a new agency and its first agency admin user.

    Supports:
    - application/json with legal_document_s3_link
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
                {key: value for key, value in form.items() if key not in {"legal_document", "legal_document_file", "legal_document_s3_link"}}
            )
            file_bytes = await upload.read()
            return service.register_with_legal_document(
                body=body,
                file_bytes=file_bytes,
                filename=upload.filename or "legal_document.pdf",
                content_type=upload.content_type,
            )

        body = AgencyRegisterRequest.model_validate(await request.json())
        return service.register(body)
    except ValidationError as exc:
        raise HTTPException(status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=exc.errors()) from exc


@router.post("/upload-document", response_model=StandardResponse[AgencyDocumentUploadResponse])
def upload_agency_document(
    body: AgencyDocumentUploadRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AgencyService, Depends(get_agency_service)],
) -> StandardResponse[AgencyDocumentUploadResponse]:
    """Return a presigned S3 upload URL for an agency legal document."""
    return service.create_document_upload(body=body, current_user=current_user)


@router.get("/list", response_model=StandardResponse[list[AgencyResponse]])
def list_agencies(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AgencyService, Depends(get_agency_service)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> StandardResponse[list[AgencyResponse]]:
    """List agencies visible to the current user."""
    return service.list_agencies(current_user=current_user, skip=skip, limit=limit)


@router.get("/{agency_id}", response_model=StandardResponse[AgencyResponse])
def get_agency(
    agency_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AgencyService, Depends(get_agency_service)],
) -> StandardResponse[AgencyResponse]:
    """Get agency details."""
    return service.get_agency(agency_id=agency_id, current_user=current_user)


@router.put("/{agency_id}", response_model=StandardResponse[AgencyResponse])
def update_agency(
    agency_id: uuid.UUID,
    body: AgencyUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AgencyService, Depends(get_agency_service)],
) -> StandardResponse[AgencyResponse]:
    """Update agency details."""
    return service.update_agency(agency_id=agency_id, body=body, current_user=current_user)


@router.delete("/{agency_id}", response_model=StandardResponse[bool])
def delete_agency(
    agency_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AgencyService, Depends(get_agency_service)],
) -> StandardResponse[bool]:
    """Delete an agency."""
    return service.delete_agency(agency_id=agency_id, current_user=current_user)
