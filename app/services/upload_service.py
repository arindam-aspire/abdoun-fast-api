"""Service layer for generating presigned upload URLs."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from app.core.config import Settings, get_settings
from app.models.user import User
from app.repositories.property_submission_repository import PropertySubmissionRepository
from app.schemas.uploads import PresignedUploadData, PresignedUploadRequest
from app.services.s3_service import S3Service
from app.utils.status_codes import HTTPStatus
from app.utils.storage_paths import (
    draft_document_key,
    draft_image_key,
    draft_owner_document_key,
    draft_video_key,
)


def _normalize_extension_set(extensions: list[str]) -> set[str]:
    """Return lowercase extensions with a leading dot for comparison with Path.suffix."""
    out: set[str] = set()
    for ext in extensions:
        e = (ext or "").strip().lower()
        if not e:
            continue
        if not e.startswith("."):
            e = f".{e}"
        out.add(e)
    return out


class UploadService:
    """Generate and validate S3 presigned upload URLs for stepper files.

    ``submission_id`` targets a persisted draft; ``draft_client_id`` (with the same path layout) is for uploads
    before a submission row exists. The route always requires an authenticated user.
    """

    def __init__(
        self,
        repository: PropertySubmissionRepository,
        s3_service: S3Service,
        settings: Settings | None = None,
    ) -> None:
        self._repo = repository
        self._s3 = s3_service
        self._settings = settings or get_settings()

    def generate_presigned_upload(
        self,
        *,
        body: PresignedUploadRequest,
        user: User,
    ) -> PresignedUploadData:
        """Validate and return a presigned PUT + public ``url`` string (no ``s3_key`` in the response)."""
        if body.submission_id is not None:
            submission = self._repo.get_submission_by_id(body.submission_id)
            if submission is None or submission.submitted_by != user.id:
                raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Submission not found")
            if getattr(submission, "deleted_at", None) is not None:
                raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Submission not found")
            if submission.status in {"approved", "rejected"}:
                raise HTTPException(
                    status_code=HTTPStatus.CONFLICT,
                    detail="Uploads are not allowed for finalized submissions",
                )
            path_id = body.submission_id
        else:
            path_id = body.draft_client_id
            if path_id is None:  # pragma: no cover — enforced by PresignedUploadRequest
                raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="draft_client_id is required")

        cleaned_name = (body.file_name or "").strip()
        if not cleaned_name:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="file_name is required")

        extension = Path(cleaned_name).suffix.lower()
        allowed_extensions = self._allowed_extensions_for_context(body.context)
        if extension not in allowed_extensions:
            allowed_str = ", ".join(sorted(allowed_extensions)) or "(none configured)"
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=(
                    f"Unsupported file extension {extension or '(missing)'} for upload context "
                    f"'{body.context}'. Allowed: {allowed_str}"
                ),
            )

        self._validate_content_type(context=body.context, content_type=body.content_type)
        self._validate_file_size(context=body.context, file_size=body.file_size)

        key = self._build_draft_key(
            context=body.context,
            path_id=path_id,
            filename=cleaned_name,
        )
        expiry = self._settings.aws_s3_presigned_expiry
        upload_url = self._s3.generate_presigned_upload_url(
            key=key,
            content_type=body.content_type,
            expires_in=expiry,
        )
        return PresignedUploadData(
            upload_url=upload_url,
            url=self._s3.build_public_url(key),
            expires_in=expiry,
        )

    def _allowed_extensions_for_context(self, context: str) -> set[str]:
        if context == "property_media_image":
            return _normalize_extension_set(self._settings.allowed_property_image_extensions)
        if context == "property_media_video":
            return _normalize_extension_set(self._settings.allowed_property_video_extensions)
        return _normalize_extension_set(self._settings.allowed_property_document_extensions)

    def _validate_content_type(self, *, context: str, content_type: str) -> None:
        lower = (content_type or "").strip().lower()
        if not lower:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="content_type is required")
        if context == "property_media_image" and not lower.startswith("image/"):
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="content_type must be image/*")
        if context == "property_media_video" and not lower.startswith("video/"):
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="content_type must be video/*")
        if context in {"owner_document", "property_document"} and "/" not in lower:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="content_type must be a valid mime type")

    def _validate_file_size(self, *, context: str, file_size: int | None) -> None:
        if file_size is None:
            return
        if file_size <= 0:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="file_size must be positive")
        limit_mb = {
            "property_media_image": self._settings.property_image_max_size_mb,
            "property_media_video": self._settings.property_video_max_size_mb,
            "property_document": self._settings.property_document_max_size_mb,
            "owner_document": self._settings.property_document_max_size_mb,
        }[context]
        limit_bytes = limit_mb * 1024 * 1024
        if file_size > limit_bytes:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=f"file_size exceeds max allowed size ({limit_mb} MB)",
            )

    def _build_draft_key(self, *, context: str, path_id, filename: str) -> str:
        """S3 key under ``drafts/property-submissions/{path_id}/...`` (submission or client draft id)."""
        if context == "property_media_image":
            return draft_image_key(path_id, filename)
        if context == "property_media_video":
            return draft_video_key(path_id, filename)
        if context == "property_document":
            return draft_document_key(path_id, filename)
        return draft_owner_document_key(path_id, filename)

