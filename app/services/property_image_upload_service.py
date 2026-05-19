"""Multipart property image upload with server-side watermarking and S3 storage."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import HTTPException

from app.core.config import Settings, get_settings
from app.exceptions.property_image_upload import PropertyImageUploadError
from app.models.user import User
from app.repositories.property_submission_repository import PropertySubmissionRepository
from app.schemas.uploads import PropertyImageUploadData
from app.services.property_image_watermark_processor import (
    PropertyImageWatermarkProcessor,
    file_extension_from_filename,
)
from app.services.s3_service import S3Service
from app.services.watermark_service import WatermarkService
from app.utils.status_codes import HTTPStatus
from app.utils.storage_paths import (
    draft_image_original_key,
    draft_image_watermarked_key,
    sanitize_filename,
)
from app.utils.upload_validation import (
    normalize_extension_set,
    resolve_draft_path_id,
    validate_property_image_file,
)

logger = logging.getLogger(__name__)


class PropertyImageUploadService:
    """Validate ownership, watermark property images, and upload to S3."""

    def __init__(
        self,
        repository: PropertySubmissionRepository,
        s3_service: S3Service,
        watermark_service: WatermarkService,
        settings: Settings | None = None,
        watermark_processor: PropertyImageWatermarkProcessor | None = None,
    ) -> None:
        self._repo = repository
        self._s3 = s3_service
        self._watermark = watermark_service
        self._settings = settings or get_settings()
        self._processor = watermark_processor or PropertyImageWatermarkProcessor(
            s3_service=s3_service,
            watermark_service=watermark_service,
            settings=self._settings,
        )

    def upload_property_image(
        self,
        *,
        user: User,
        file_bytes: bytes,
        filename: str | None,
        content_type: str | None,
        submission_id: uuid.UUID | None,
        draft_client_id: uuid.UUID | None,
    ) -> PropertyImageUploadData:
        """Store original, generate watermarked copy, return watermarked public URL."""
        path_id = resolve_draft_path_id(
            submission_id=submission_id,
            draft_client_id=draft_client_id,
        )

        if submission_id is not None:
            self._assert_submission_upload_allowed(submission_id=submission_id, user=user)
            log_id = str(submission_id)
        else:
            log_id = f"draft_client_id={draft_client_id}"

        cleaned_name, extension = validate_property_image_file(
            filename=filename,
            content_type=content_type,
            file_bytes=file_bytes,
            allowed_extensions=self._settings.allowed_property_image_extensions,
            max_size_mb=self._settings.property_image_max_size_mb,
        )
        sanitized_name = sanitize_filename(cleaned_name)
        original_key = draft_image_original_key(path_id, sanitized_name)
        watermarked_key = draft_image_watermarked_key(path_id, sanitized_name)

        logger.info(
            "[property_image] upload started user_id=%s %s file_name=%s input_bytes=%s",
            user.id,
            log_id,
            sanitized_name,
            len(file_bytes),
        )

        try:
            self._s3.put_object(
                key=original_key,
                body=file_bytes,
                content_type=content_type or "application/octet-stream",
            )
            ok = self._processor.process_now(
                original_key=original_key,
                watermarked_key=watermarked_key,
                file_extension=extension,
                wait_for_original=False,
            )
            if not ok:
                raise PropertyImageUploadError(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    message="Watermark processing failed",
                    detail="Could not create watermarked copy",
                )
            public_url = self._s3.build_public_url(watermarked_key)
            original_url = self._s3.build_public_url(original_key)
        except PropertyImageUploadError:
            raise
        except HTTPException as exc:
            raise PropertyImageUploadError(
                status_code=exc.status_code,
                message="Upload failed",
                detail=str(exc.detail),
            ) from exc
        except Exception as exc:
            logger.exception("[property_image] upload failed user_id=%s %s", user.id, log_id)
            raise PropertyImageUploadError(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                message="Upload failed",
                detail=str(exc),
            ) from exc

        logger.info(
            "[property_image] upload succeeded user_id=%s %s watermarked_key=%s",
            user.id,
            log_id,
            watermarked_key,
        )
        return PropertyImageUploadData(
            url=public_url,
            file_name=sanitized_name,
            original_url=original_url,
        )

    def finalize_presigned_property_image(
        self,
        *,
        user: User,
        filename: str,
        submission_id: uuid.UUID | None,
        draft_client_id: uuid.UUID | None,
    ) -> PropertyImageUploadData:
        """Retry watermark job for presigned flow (optional; processing is normally automatic)."""
        path_id = resolve_draft_path_id(
            submission_id=submission_id,
            draft_client_id=draft_client_id,
        )

        if submission_id is not None:
            self._assert_submission_upload_allowed(submission_id=submission_id, user=user)

        cleaned_name = (filename or "").strip().split("/")[-1].split("\\")[-1]
        if not cleaned_name:
            raise PropertyImageUploadError(
                status_code=HTTPStatus.BAD_REQUEST,
                message="Invalid file",
                detail="file_name is required",
            )

        extension = Path(cleaned_name).suffix.lower()
        if extension not in normalize_extension_set(self._settings.allowed_property_image_extensions):
            raise PropertyImageUploadError(
                status_code=HTTPStatus.BAD_REQUEST,
                message="Invalid file extension",
                detail=f"Unsupported extension: {extension}",
            )

        sanitized_name = sanitize_filename(cleaned_name)
        original_key = draft_image_original_key(path_id, sanitized_name)
        watermarked_key = draft_image_watermarked_key(path_id, sanitized_name)

        if not self._s3.object_exists(key=original_key):
            raise PropertyImageUploadError(
                status_code=HTTPStatus.NOT_FOUND,
                message="Image not found",
                detail="Upload the original to S3 before finalizing",
            )

        ok = self._processor.process_now(
            original_key=original_key,
            watermarked_key=watermarked_key,
            file_extension=extension,
            wait_for_original=False,
        )
        if not ok:
            raise PropertyImageUploadError(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                message="Finalize failed",
                detail="Watermark processing failed",
            )

        return PropertyImageUploadData(
            url=self._s3.build_public_url(watermarked_key),
            file_name=sanitized_name,
            original_url=self._s3.build_public_url(original_key),
        )

    def _assert_submission_upload_allowed(self, *, submission_id: uuid.UUID, user: User) -> None:
        submission = self._repo.get_submission_by_id(submission_id)
        if submission is None or getattr(submission, "deleted_at", None) is not None:
            raise PropertyImageUploadError(
                status_code=HTTPStatus.NOT_FOUND,
                message="Submission not found",
                detail="No submission exists for the given submission_id",
            )
        if submission.submitted_by != user.id:
            raise PropertyImageUploadError(
                status_code=HTTPStatus.FORBIDDEN,
                message="Forbidden",
                detail="submission_id does not belong to the authenticated user",
            )
        if submission.status in {"approved", "rejected"}:
            raise PropertyImageUploadError(
                status_code=HTTPStatus.CONFLICT,
                message="Submission locked",
                detail="Uploads are not allowed for finalized submissions",
            )
