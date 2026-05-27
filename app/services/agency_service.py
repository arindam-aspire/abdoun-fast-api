"""Agency registration, CRUD, and legal-document upload workflow."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import HTTPException

from app.models.agency import Agency
from app.models.user import User
from app.repositories.agency_repository import AgencyRepository
from app.schemas.agency import (
    AgencyDocumentUploadRequest,
    AgencyDocumentUploadResponse,
    AgencyRegisterMultipartRequest,
    AgencyRegisterRequest,
    AgencyRegisterResponse,
    AgencyResponse,
    AgencyUpdateRequest,
)
from app.schemas.user import UserResponse
from app.services.cognito import cognito_service
from app.services.s3_service import S3Service
from app.utils.agency_security import hash_password
from app.utils.constants import CognitoConstants, ErrorMessages, SuccessMessages, UserRoles
from app.utils.responses import StandardResponse, create_success_response
from app.utils.status_codes import HTTPStatus
from app.utils.storage_paths import sanitize_filename


class AgencyService:
    """Business logic for agency registration and agency-scoped management."""

    def __init__(self, repository: AgencyRepository, s3_service: S3Service | None = None) -> None:
        self._repo = repository
        self._s3 = s3_service or S3Service()

    def _ensure_roles(self) -> None:
        self._repo.add_roles_if_missing(
            [
                (UserRoles.SUPER_ADMIN, "Platform super administrator"),
                (UserRoles.ADMIN, "Administrator"),
            ]
        )

    def _assert_can_manage_agency(self, *, current_user: User, agency_id: uuid.UUID) -> None:
        roles = {role.name for role in current_user.roles}
        if UserRoles.SUPER_ADMIN in roles:
            return
        if UserRoles.ADMIN in roles and (current_user.agency_id is None or current_user.agency_id == agency_id):
            return
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail=ErrorMessages.AGENCY_ACCESS_DENIED)

    def _legal_document_key(self, *, agency_id: uuid.UUID, filename: str) -> str:
        return f"{agency_id}/profile_doc/{sanitize_filename(filename)}"

    def _validate_pdf_document(self, *, filename: str, content_type: str | None, body: bytes) -> None:
        if not body:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="legal document PDF is required")
        if Path(filename).suffix.lower() != ".pdf":
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="legal document must be a PDF file")
        if content_type and content_type.lower() not in {"application/pdf", "application/octet-stream"}:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="legal document content_type must be application/pdf")

    def _register(
        self,
        *,
        body: AgencyRegisterRequest | AgencyRegisterMultipartRequest,
        legal_document_s3_link: str | None = None,
        legal_document_file: bytes | None = None,
        legal_document_filename: str | None = None,
        legal_document_content_type: str | None = None,
    ) -> StandardResponse[AgencyRegisterResponse]:
        email = str(body.email).lower()
        if self._repo.agency_exists_by_email_or_phone(email=email, phone=body.phone):
            raise HTTPException(status_code=HTTPStatus.CONFLICT, detail=ErrorMessages.AGENCY_EXISTS)
        if self._repo.user_exists_by_email(email):
            raise HTTPException(status_code=HTTPStatus.CONFLICT, detail=ErrorMessages.USER_EXISTS)

        try:
            self._ensure_roles()
            cognito_response = cognito_service.signup(
                email=email,
                password=body.password,
                full_name=body.agency_trade_name or body.agency_name,
                phone_number=body.phone,
            )
            cognito_sub = cognito_response.get(CognitoConstants.USER_SUB)
            if not cognito_sub:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=ErrorMessages.COGNITO_SIGNUP_MISSING_USERSUB,
                )
            agency = self._repo.create_agency(
                agency_name=body.agency_name,
                agency_trade_name=body.agency_trade_name,
                legal_document_s3_link=legal_document_s3_link or "__pending_legal_document_upload__",
                email=email,
                phone=body.phone,
                website=str(body.website) if body.website else None,
                address=body.address,
                city=body.city,
                state=body.state,
                country=body.country,
                zip_code=body.zip_code,
                is_active=True,
                is_verified=False,
            )
            user = self._repo.create_user(
                email=email,
                cognito_sub=cognito_sub,
                full_name=body.agency_trade_name or body.agency_name,
                phone_number=body.phone,
                agency_id=agency.id,
                password_hash=hash_password(body.password),
                is_active=True,
                is_email_verified=False,
                is_phone_verified=False,
            )
            role = self._repo.get_role_by_name(UserRoles.ADMIN)
            if role:
                user.roles.append(role)

            if legal_document_file is not None:
                filename = legal_document_filename or "legal_document.pdf"
                self._validate_pdf_document(
                    filename=filename,
                    content_type=legal_document_content_type,
                    body=legal_document_file,
                )
                key = self._legal_document_key(agency_id=agency.id, filename=filename)
                self._s3.put_object(
                    key=key,
                    body=legal_document_file,
                    content_type=legal_document_content_type or "application/pdf",
                )
                agency.legal_document_s3_link = self._s3.build_public_url(key)

            # Placeholder: dispatch verification email/SMS for agency onboarding.
            self._repo.commit()
            self._repo.refresh(agency)
            self._repo.refresh(user)
            data = AgencyRegisterResponse(
                agency=AgencyResponse.model_validate(agency),
                user=UserResponse.model_validate(user),
            )
            return create_success_response(data=data, message=SuccessMessages.AGENCY_REGISTERED)
        except HTTPException:
            self._repo.rollback()
            raise
        except Exception as exc:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=ErrorMessages.REGISTRATION_FAILED) from exc

    def register(self, body: AgencyRegisterRequest) -> StandardResponse[AgencyRegisterResponse]:
        return self._register(body=body, legal_document_s3_link=body.legal_document_s3_link)

    def register_with_legal_document(
        self,
        *,
        body: AgencyRegisterMultipartRequest,
        file_bytes: bytes,
        filename: str,
        content_type: str | None,
    ) -> StandardResponse[AgencyRegisterResponse]:
        return self._register(
            body=body,
            legal_document_file=file_bytes,
            legal_document_filename=filename,
            legal_document_content_type=content_type,
        )

    def get_agency(self, *, agency_id: uuid.UUID, current_user: User) -> StandardResponse[AgencyResponse]:
        self._assert_can_manage_agency(current_user=current_user, agency_id=agency_id)
        agency = self._repo.get_by_id(agency_id)
        if not agency:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.AGENCY_NOT_FOUND)
        return create_success_response(data=AgencyResponse.model_validate(agency), message=None)

    def list_agencies(self, *, current_user: User, skip: int, limit: int) -> StandardResponse[list[AgencyResponse]]:
        roles = {role.name for role in current_user.roles}
        if UserRoles.SUPER_ADMIN in roles or (UserRoles.ADMIN in roles and current_user.agency_id is None):
            agencies = self._repo.list_agencies(skip=skip, limit=limit)
        elif UserRoles.ADMIN in roles and current_user.agency_id:
            agency = self._repo.get_by_id(current_user.agency_id)
            agencies = [agency] if agency else []
        else:
            raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail=ErrorMessages.AGENCY_ACCESS_DENIED)
        return create_success_response(data=[AgencyResponse.model_validate(a) for a in agencies], message=None)

    def update_agency(
        self, *, agency_id: uuid.UUID, body: AgencyUpdateRequest, current_user: User
    ) -> StandardResponse[AgencyResponse]:
        self._assert_can_manage_agency(current_user=current_user, agency_id=agency_id)
        agency = self._repo.get_by_id(agency_id)
        if not agency:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.AGENCY_NOT_FOUND)
        values = body.model_dump(exclude_unset=True)
        if "website" in values and values["website"] is not None:
            values["website"] = str(values["website"])
        if "phone" in values and values["phone"] != agency.phone:
            if self._repo.agency_phone_exists_excluding(phone=values["phone"], exclude_agency_id=agency.id):
                raise HTTPException(status_code=HTTPStatus.CONFLICT, detail=ErrorMessages.AGENCY_EXISTS)
        for key, value in values.items():
            setattr(agency, key, value)
        self._repo.commit()
        self._repo.refresh(agency)
        return create_success_response(data=AgencyResponse.model_validate(agency), message=SuccessMessages.AGENCY_UPDATED)

    def delete_agency(self, *, agency_id: uuid.UUID, current_user: User) -> StandardResponse[bool]:
        self._assert_can_manage_agency(current_user=current_user, agency_id=agency_id)
        agency = self._repo.get_by_id(agency_id)
        if not agency:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.AGENCY_NOT_FOUND)
        self._repo.delete_agency(agency)
        self._repo.commit()
        return create_success_response(data=True, message=SuccessMessages.AGENCY_DELETED)

    def create_document_upload(
        self, *, body: AgencyDocumentUploadRequest, current_user: User
    ) -> StandardResponse[AgencyDocumentUploadResponse]:
        if not current_user.agency_id:
            raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail=ErrorMessages.AGENCY_ACCESS_DENIED)
        suffix = Path(body.file_name).suffix.lower()
        if suffix not in {".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg"}:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Unsupported legal document type")
        key = self._legal_document_key(agency_id=current_user.agency_id, filename=body.file_name)
        upload_url = self._s3.generate_presigned_upload_url(key=key, content_type=body.content_type)
        public_url = self._s3.build_public_url(key)
        from app.core.config import get_settings

        return create_success_response(
            data=AgencyDocumentUploadResponse(
                upload_url=upload_url,
                legal_document_s3_link=public_url,
                expires_in=get_settings().aws_s3_presigned_expiry,
            ),
            message=SuccessMessages.AGENCY_DOCUMENT_UPLOAD_READY,
        )
