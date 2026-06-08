"""Presigned S3 upload flow for agency logos (mirrors profile picture upload)."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import HTTPException

from app.core.config import Settings, get_settings
from app.models.agency import Agency
from app.models.user import User
from app.repositories.agency_repository import AgencyRepository
from app.schemas.agency import AgencyLogoGetResponse, AgencyLogoUploadRequest, AgencyLogoUploadResponse
from app.services.s3_service import S3Service
from app.services.upload_service import _normalize_extension_set
from app.utils.constants import ErrorMessages, UserRoles
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.logger import api_logger
from app.utils.s3_stored_url import extract_s3_object_key
from app.utils.status_codes import HTTPStatus
from app.utils.storage_paths import agency_logo_key


class AgencyLogoUploadService:
    """Agency logo presigned upload, replacement (S3 delete + new key), and retrieval."""

    def __init__(
        self,
        repository: AgencyRepository,
        s3_service: S3Service,
        settings: Settings | None = None,
    ) -> None:
        self._repo = repository
        self._s3 = s3_service
        self._settings = settings or get_settings()

    def _assert_can_manage_agency(self, *, current_user: User, agency_id: uuid.UUID) -> None:
        roles = {role.name for role in current_user.roles}
        if UserRoles.SUPER_ADMIN in roles:
            return
        if UserRoles.ADMIN in roles and (
            current_user.agency_id is None or current_user.agency_id == agency_id
        ):
            return
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail=ErrorMessages.AGENCY_ACCESS_DENIED)

    def _get_agency_or_404(self, agency_id: uuid.UUID) -> Agency:
        agency = self._repo.get_by_id(agency_id)
        if not agency:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.AGENCY_NOT_FOUND)
        return agency

    def _delete_stored_logo_if_any(self, agency: Agency) -> None:
        """Remove previous logo object from S3 when replacing (best-effort)."""
        stored = (agency.logo_url or "").strip()
        if not stored:
            return
        key = extract_s3_object_key(stored, self._settings)
        if not key:
            return
        try:
            if self._s3.object_exists(key=key):
                self._s3.delete_object(key=key)
        except Exception as exc:  # pragma: no cover - boto/network
            api_logger.warning(
                format_log_message(
                    LogMessages.MediaUrlSigner.PRESIGNED_GET_FAILED,
                    error=f"agency logo delete failed key={key}: {exc}",
                )
            )

    def _validate_logo_metadata(
        self, *, file_name: str, content_type: str, file_size: int | None
    ) -> str:
        cleaned_name = (file_name or "").strip()
        if not cleaned_name:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="file_name is required")

        extension = Path(cleaned_name).suffix.lower()
        allowed_extensions = _normalize_extension_set(self._settings.allowed_property_image_extensions)
        if extension not in allowed_extensions:
            allowed_str = ", ".join(sorted(allowed_extensions)) or "(none configured)"
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=(
                    f"Unsupported file extension {extension or '(missing)'} for agency logo upload. "
                    f"Allowed: {allowed_str}"
                ),
            )

        lower_ct = (content_type or "").strip().lower()
        if not lower_ct:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="content_type is required")
        if not lower_ct.startswith("image/"):
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="content_type must be image/*")

        if file_size is not None:
            if file_size <= 0:
                raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="file_size must be positive")
            limit_mb = self._settings.property_image_max_size_mb
            limit_bytes = limit_mb * 1024 * 1024
            if file_size > limit_bytes:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=f"file_size exceeds max allowed size ({limit_mb} MB)",
                )
        return cleaned_name

    def initiate_upload(
        self,
        *,
        agency_id: uuid.UUID,
        current_user: User,
        body: AgencyLogoUploadRequest,
    ) -> AgencyLogoUploadResponse:
        """Presigned PUT flow (same as POST /auth/me/profile-picture)."""
        self._assert_can_manage_agency(current_user=current_user, agency_id=agency_id)
        agency = self._get_agency_or_404(agency_id)

        cleaned_name = self._validate_logo_metadata(
            file_name=body.file_name,
            content_type=body.content_type,
            file_size=body.file_size,
        )
        self._delete_stored_logo_if_any(agency)

        key = agency_logo_key(agency.id, cleaned_name)
        public_url = self._s3.build_public_url(key)
        put_expiry = self._settings.aws_s3_presigned_expiry
        upload_url = self._s3.generate_presigned_upload_url(
            key=key,
            content_type=body.content_type,
            expires_in=put_expiry,
        )

        agency.logo_url = public_url
        self._repo.commit()
        self._repo.refresh(agency)

        return AgencyLogoUploadResponse(
            logo_url=public_url,
            upload_url=upload_url,
            expires_in=put_expiry,
        )

    def upload_logo_file(
        self,
        *,
        agency_id: uuid.UUID,
        current_user: User,
        file_bytes: bytes,
        filename: str,
        content_type: str | None,
    ) -> AgencyLogoUploadResponse:
        """Server-side upload when client sends multipart image (deletes prior logo first)."""
        if not file_bytes:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="logo image file is required")

        body = AgencyLogoUploadRequest(
            file_name=filename or "logo.png",
            content_type=content_type or "image/png",
            file_size=len(file_bytes),
        )
        self._assert_can_manage_agency(current_user=current_user, agency_id=agency_id)
        agency = self._get_agency_or_404(agency_id)

        cleaned_name = self._validate_logo_metadata(
            file_name=body.file_name,
            content_type=body.content_type,
            file_size=len(file_bytes),
        )
        self._delete_stored_logo_if_any(agency)

        key = agency_logo_key(agency.id, cleaned_name)
        self._s3.put_object(key=key, body=file_bytes, content_type=body.content_type)
        public_url = self._s3.build_public_url(key)
        agency.logo_url = public_url
        self._repo.commit()
        self._repo.refresh(agency)

        get_expiry = self._settings.aws_s3_presigned_get_expiry_seconds
        return AgencyLogoUploadResponse(
            logo_url=public_url,
            upload_url="",
            expires_in=get_expiry,
        )

    def get_logo(
        self,
        *,
        agency_id: uuid.UUID,
        current_user: User,
    ) -> AgencyLogoGetResponse:
        """Return presigned GET URL for the agency logo stored in the database."""
        self._assert_can_manage_agency(current_user=current_user, agency_id=agency_id)
        agency = self._get_agency_or_404(agency_id)

        stored = (agency.logo_url or "").strip()
        if not stored:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.AGENCY_LOGO_NOT_FOUND)

        key = extract_s3_object_key(stored, self._settings)
        if key is None:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.AGENCY_LOGO_NOT_FOUND)

        expiry = self._settings.aws_s3_presigned_get_expiry_seconds
        presigned = self._s3.generate_presigned_get_url(key=key, expires_in=expiry)
        return AgencyLogoGetResponse(logo_url=presigned, expires_in=expiry)

    def delete_logo(self, *, agency_id: uuid.UUID, current_user: User) -> bool:
        """Delete logo object from S3 and clear agency_master.logo_url."""
        self._assert_can_manage_agency(current_user=current_user, agency_id=agency_id)
        agency = self._get_agency_or_404(agency_id)

        stored = (agency.logo_url or "").strip()
        if not stored:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=ErrorMessages.AGENCY_LOGO_NOT_FOUND)

        self._delete_stored_logo_if_any(agency)
        agency.logo_url = None
        self._repo.commit()
        return True
