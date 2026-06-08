"""Agency registration, CRUD, and legal-document upload workflow."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import HTTPException

from app.models.agency import Agency
from app.models.user import User
from app.repositories.agency_repository import AgencyRepository
from app.core.config import get_settings
from app.schemas.agency import (
    AgencyDocumentUploadRequest,
    AgencyDocumentUploadResponse,
    AgencyLegalDocumentUploadData,
    AgencyRegisterMultipartRequest,
    AgencyRegisterRequest,
    AgencyRegisterResponse,
    AgencyResponse,
    AgencyUpdateRequest,
    AgencyUpdateResult,
)
from app.schemas.user import UserResponse
from app.services.cognito import cognito_service
from app.services.s3_service import S3Service
from app.utils.agency_security import hash_password
from app.utils.constants import CognitoConstants, Defaults, ErrorMessages, SuccessMessages, UserRoles
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

    def _to_agency_response(
        self,
        agency: Agency,
        *,
        profile_picture_map: dict[uuid.UUID, str] | None = None,
    ) -> AgencyResponse:
        data = AgencyResponse.model_validate(agency)
        if profile_picture_map:
            data.profile_picture_url = profile_picture_map.get(agency.id, "") or ""
        return data

    def _legal_document_key(self, *, agency_id: uuid.UUID, filename: str) -> str:
        return f"{agency_id}/profile_doc/{sanitize_filename(filename)}"

    def _validate_pdf_document(self, *, filename: str, content_type: str | None, body: bytes) -> None:
        if not body:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="legal document PDF is required")
        if Path(filename).suffix.lower() != ".pdf":
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="legal document must be a PDF file")
        if content_type and content_type.lower() not in {"application/pdf", "application/octet-stream"}:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="legal document content_type must be application/pdf")

    def _validate_legal_document_presign_metadata(
        self, *, file_name: str, content_type: str, file_size: int | None
    ) -> None:
        cleaned_name = (file_name or "").strip()
        if not cleaned_name:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="file_name is required")
        if Path(cleaned_name).suffix.lower() != ".pdf":
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="legal document must be a PDF file")
        lower_ct = (content_type or "").strip().lower()
        if not lower_ct:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="content_type is required")
        if lower_ct not in {"application/pdf", "application/octet-stream"}:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="legal document content_type must be application/pdf",
            )
        if file_size is not None:
            if file_size <= 0:
                raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="file_size must be positive")
            limit_mb = get_settings().property_image_max_size_mb
            limit_bytes = limit_mb * 1024 * 1024
            if file_size > limit_bytes:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=f"file_size exceeds max allowed size ({limit_mb} MB)",
                )

    def _initiate_legal_document_presign(
        self,
        *,
        agency: Agency,
        file_name: str,
        content_type: str,
        file_size: int | None = None,
    ) -> AgencyLegalDocumentUploadData:
        self._validate_legal_document_presign_metadata(
            file_name=file_name,
            content_type=content_type,
            file_size=file_size,
        )
        key = self._legal_document_key(agency_id=agency.id, filename=file_name)
        public_url = self._s3.build_public_url(key)
        expiry = get_settings().aws_s3_presigned_expiry
        upload_url = self._s3.generate_presigned_upload_url(
            key=key,
            content_type=content_type,
            expires_in=expiry,
        )
        agency.legal_document_s3_link = public_url
        return AgencyLegalDocumentUploadData(
            legal_document_s3_link=public_url,
            upload_url=upload_url,
            expires_in=expiry,
        )

    def _register(
        self,
        *,
        body: AgencyRegisterRequest | AgencyRegisterMultipartRequest,
        legal_document_presign: tuple[str, str, int | None] | None = None,
        legal_document_file: bytes | None = None,
        legal_document_filename: str | None = None,
        legal_document_content_type: str | None = None,
    ) -> StandardResponse[AgencyRegisterResponse]:
        email = str(body.email).lower()
        if self._repo.agency_exists_by_email_or_phone(email=email, phone=body.phone_number):
            raise HTTPException(status_code=HTTPStatus.CONFLICT, detail=ErrorMessages.AGENCY_EXISTS)
        if self._repo.user_exists_by_email(email):
            raise HTTPException(status_code=HTTPStatus.CONFLICT, detail=ErrorMessages.USER_EXISTS)

        try:
            self._ensure_roles()
            cognito_response = cognito_service.signup(
                email=email,
                password=body.password,
                full_name=body.agency_trade_name or body.agency_name,
                phone_number=body.phone_number,
            )
            cognito_sub = cognito_response.get(CognitoConstants.USER_SUB)
            if not cognito_sub:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=ErrorMessages.COGNITO_SIGNUP_MISSING_USERSUB,
                )
            register_currency = (body.currency or Defaults.DEFAULT_CURRENCY).strip().upper()
            register_measurement_unit = (
                body.measurement_unit or Defaults.DEFAULT_MEASUREMENT_UNIT
            ).strip().lower()
            agency = self._repo.create_agency(
                agency_name=body.agency_name,
                agency_trade_name=body.agency_trade_name,
                legal_document_s3_link="__pending_legal_document_upload__",
                email=email,
                phone=body.phone_number,
                website=str(body.website) if body.website else None,
                address=body.address,
                city=body.city,
                state=body.state,
                country=body.country,
                zip_code=body.zip_code,
                currency=register_currency,
                measurement_unit=register_measurement_unit,
                is_active=True,
                is_verified=False,
            )
            user = self._repo.create_user(
                email=email,
                cognito_sub=cognito_sub,
                full_name=body.agency_trade_name or body.agency_name,
                phone_number=body.phone_number,
                agency_id=agency.id,
                password_hash=hash_password(body.password),
                is_active=True,
                is_email_verified=False,
                is_phone_verified=False,
            )
            role = self._repo.get_role_by_name(UserRoles.ADMIN)
            if role:
                user.roles.append(role)

            legal_upload: AgencyLegalDocumentUploadData | None = None
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
            elif legal_document_presign is not None:
                file_name, content_type, file_size = legal_document_presign
                legal_upload = self._initiate_legal_document_presign(
                    agency=agency,
                    file_name=file_name,
                    content_type=content_type,
                    file_size=file_size,
                )

            # Placeholder: dispatch verification email/SMS for agency onboarding.
            self._repo.commit()
            self._repo.refresh(agency)
            self._repo.refresh(user)
            data = AgencyRegisterResponse(
                agency=AgencyResponse.model_validate(agency),
                user=UserResponse.model_validate(user),
                legal_document_upload=legal_upload,
            )
            return create_success_response(data=data, message=SuccessMessages.AGENCY_REGISTERED)
        except HTTPException:
            self._repo.rollback()
            raise
        except Exception as exc:
            self._repo.rollback()
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=ErrorMessages.REGISTRATION_FAILED) from exc

    def register(self, body: AgencyRegisterRequest) -> StandardResponse[AgencyRegisterResponse]:
        return self._register(
            body=body,
            legal_document_presign=(body.file_name, body.content_type, body.file_size),
        )

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
        picture_map = self._repo.get_profile_picture_map_for_agencies([agency.id])
        return create_success_response(
            data=self._to_agency_response(agency, profile_picture_map=picture_map),
            message=None,
        )

    def list_agencies(self, *, current_user: User, skip: int, limit: int) -> StandardResponse[list[AgencyResponse]]:
        roles = {role.name for role in current_user.roles}
        if UserRoles.SUPER_ADMIN in roles or (UserRoles.ADMIN in roles and current_user.agency_id is None):
            agencies = self._repo.list_agencies(skip=skip, limit=limit)
        elif UserRoles.ADMIN in roles and current_user.agency_id:
            agency = self._repo.get_by_id(current_user.agency_id)
            agencies = [agency] if agency else []
        else:
            raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail=ErrorMessages.AGENCY_ACCESS_DENIED)
        valid_agencies = [a for a in agencies if a is not None]
        picture_map = self._repo.get_profile_picture_map_for_agencies([a.id for a in valid_agencies])
        return create_success_response(
            data=[
                self._to_agency_response(a, profile_picture_map=picture_map)
                for a in valid_agencies
            ],
            message=None,
        )

    def update_agency(
        self,
        *,
        agency_id: uuid.UUID,
        body: AgencyUpdateRequest,
        current_user: User,
        legal_document_file: bytes | None = None,
        legal_document_filename: str | None = None,
        legal_document_content_type: str | None = None,
    ) -> StandardResponse[AgencyUpdateResult]:
        self._assert_can_manage_agency(current_user=current_user, agency_id=agency_id)
        agency = self._repo.get_by_id(agency_id)
        if not agency:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.AGENCY_NOT_FOUND)

        legal_upload: AgencyLegalDocumentUploadData | None = None
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
        elif body.legal_document_file_name and body.legal_document_content_type:
            legal_upload = self._initiate_legal_document_presign(
                agency=agency,
                file_name=body.legal_document_file_name,
                content_type=body.legal_document_content_type,
                file_size=body.legal_document_file_size,
            )

        values = body.model_dump(
            exclude_unset=True,
            exclude_none=True,
            exclude={
                "legal_document_file_name",
                "legal_document_content_type",
                "legal_document_file_size",
            },
        )
        if "website" in values and values["website"] is not None:
            values["website"] = str(values["website"])
        if "phone" in values and values["phone"] != agency.phone:
            if self._repo.agency_phone_exists_excluding(phone=values["phone"], exclude_agency_id=agency.id):
                raise HTTPException(status_code=HTTPStatus.CONFLICT, detail=ErrorMessages.AGENCY_EXISTS)
        for key, value in values.items():
            setattr(agency, key, value)
        self._repo.commit()
        self._repo.refresh(agency)
        picture_map = self._repo.get_profile_picture_map_for_agencies([agency.id])
        return create_success_response(
            data=AgencyUpdateResult(
                agency=self._to_agency_response(agency, profile_picture_map=picture_map),
                legal_document_upload=legal_upload,
            ),
            message=SuccessMessages.AGENCY_UPDATED,
        )

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
        agency = self._repo.get_by_id(current_user.agency_id)
        if not agency:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.AGENCY_NOT_FOUND)
        suffix = Path(body.file_name).suffix.lower()
        if suffix not in {".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg"}:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Unsupported legal document type")
        upload_data = self._initiate_legal_document_presign(
            agency=agency,
            file_name=body.file_name,
            content_type=body.content_type,
            file_size=body.file_size,
        )
        self._repo.commit()
        self._repo.refresh(agency)
        return create_success_response(
            data=AgencyDocumentUploadResponse(
                upload_url=upload_data.upload_url,
                legal_document_s3_link=upload_data.legal_document_s3_link,
                expires_in=upload_data.expires_in,
            ),
            message=SuccessMessages.AGENCY_DOCUMENT_UPLOAD_READY,
        )
