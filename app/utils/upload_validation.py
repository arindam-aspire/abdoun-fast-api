"""Shared validation helpers for property media uploads."""

from __future__ import annotations

import uuid
from pathlib import Path

from app.exceptions.property_image_upload import PropertyImageUploadError
from app.utils.status_codes import HTTPStatus


def normalize_extension_set(extensions: list[str]) -> set[str]:
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


def resolve_draft_path_id(
    *,
    submission_id: uuid.UUID | None,
    draft_client_id: uuid.UUID | None,
) -> uuid.UUID:
    """Require exactly one of submission_id or draft_client_id (XOR)."""
    has_submission = submission_id is not None
    has_draft = draft_client_id is not None
    if has_submission and has_draft:
        raise PropertyImageUploadError(
            status_code=HTTPStatus.BAD_REQUEST,
            message="Invalid request",
            detail="Provide only one of submission_id or draft_client_id",
        )
    if not has_submission and not has_draft:
        raise PropertyImageUploadError(
            status_code=HTTPStatus.BAD_REQUEST,
            message="Invalid request",
            detail="Provide exactly one of submission_id or draft_client_id",
        )
    return submission_id if submission_id is not None else draft_client_id  # type: ignore[return-value]


def validate_property_image_file(
    *,
    filename: str | None,
    content_type: str | None,
    file_bytes: bytes,
    allowed_extensions: list[str],
    max_size_mb: int,
) -> tuple[str, str]:
    """Validate filename, extension, MIME type, and size. Returns (sanitized_name, extension)."""
    if not file_bytes:
        raise PropertyImageUploadError(
            status_code=HTTPStatus.BAD_REQUEST,
            message="Invalid file",
            detail="file is missing or empty",
        )

    cleaned_name = (filename or "").strip().split("/")[-1].split("\\")[-1]
    if not cleaned_name:
        raise PropertyImageUploadError(
            status_code=HTTPStatus.BAD_REQUEST,
            message="Invalid file",
            detail="file name is required",
        )

    extension = Path(cleaned_name).suffix.lower()
    allowed = normalize_extension_set(allowed_extensions)
    if extension not in allowed:
        allowed_str = ", ".join(sorted(allowed)) or "(none configured)"
        raise PropertyImageUploadError(
            status_code=HTTPStatus.BAD_REQUEST,
            message="Invalid file extension",
            detail=f"Allowed extensions: {allowed_str}",
        )

    mime = (content_type or "").strip().lower()
    if not mime.startswith("image/"):
        raise PropertyImageUploadError(
            status_code=HTTPStatus.BAD_REQUEST,
            message="Invalid content type",
            detail="content_type must be image/*",
        )

    limit_bytes = max_size_mb * 1024 * 1024
    if len(file_bytes) > limit_bytes:
        raise PropertyImageUploadError(
            status_code=HTTPStatus.BAD_REQUEST,
            message="File too large",
            detail=f"Maximum allowed size is {max_size_mb} MB",
        )

    return cleaned_name, extension
