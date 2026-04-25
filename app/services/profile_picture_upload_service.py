"""Presigned S3 upload flow for the current user's profile picture (mirrors property image presigned validation)."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from app.core.config import Settings, get_settings
from app.models.user import User
from app.repositories.auth_repository import AuthRepository
from app.schemas.user import ProfilePictureUploadData, ProfilePictureUploadRequest
from app.services.s3_service import S3Service
from app.services.upload_service import _normalize_extension_set
from app.utils.status_codes import HTTPStatus
from app.utils.storage_paths import user_profile_picture_key


class ProfilePictureUploadService:
    """Generate presigned profile-picture uploads and persist the resulting public URL on the user."""

    def __init__(
        self,
        repository: AuthRepository,
        s3_service: S3Service,
        settings: Settings | None = None,
    ) -> None:
        self._repo = repository
        self._s3 = s3_service
        self._settings = settings or get_settings()

    def initiate_upload(self, *, user: User, body: ProfilePictureUploadRequest) -> ProfilePictureUploadData:
        cleaned_name = (body.file_name or "").strip()
        if not cleaned_name:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="file_name is required")

        extension = Path(cleaned_name).suffix.lower()
        allowed_extensions = _normalize_extension_set(self._settings.allowed_property_image_extensions)
        if extension not in allowed_extensions:
            allowed_str = ", ".join(sorted(allowed_extensions)) or "(none configured)"
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=(
                    f"Unsupported file extension {extension or '(missing)'} for profile picture upload. "
                    f"Allowed: {allowed_str}"
                ),
            )

        lower_ct = (body.content_type or "").strip().lower()
        if not lower_ct:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="content_type is required")
        if not lower_ct.startswith("image/"):
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="content_type must be image/*")

        self._validate_file_size(file_size=body.file_size)

        key = user_profile_picture_key(user.id, cleaned_name)
        public_url = self._s3.build_public_url(key)
        expiry = self._settings.aws_s3_presigned_expiry
        upload_url = self._s3.generate_presigned_upload_url(
            key=key,
            content_type=body.content_type,
            expires_in=expiry,
        )

        user.profile_picture_url = public_url
        self._repo.commit()
        self._repo.refresh(user)

        return ProfilePictureUploadData(
            profile_picture_url=public_url,
            upload_url=upload_url,
            expires_in=expiry,
        )

    def _validate_file_size(self, *, file_size: int | None) -> None:
        if file_size is None:
            return
        if file_size <= 0:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="file_size must be positive")
        limit_mb = self._settings.property_image_max_size_mb
        limit_bytes = limit_mb * 1024 * 1024
        if file_size > limit_bytes:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=f"file_size exceeds max allowed size ({limit_mb} MB)",
            )
