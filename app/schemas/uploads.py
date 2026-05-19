"""Schemas for upload helper endpoints."""

import uuid
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


UploadContext = Literal[
    "owner_document",
    "property_media_image",
    "property_media_video",
    "property_document",
]


class PresignedUploadRequest(BaseModel):
    """Request payload for generating a presigned upload URL.

    Provide exactly one of ``submission_id`` (saved draft) or ``draft_client_id`` (local-only id before a submission row exists).
    """

    submission_id: uuid.UUID | None = None
    draft_client_id: uuid.UUID | None = None
    context: UploadContext
    file_name: str
    content_type: str
    file_size: int | None = None

    @model_validator(mode="after")
    def exactly_one_draft_key(self) -> Self:
        has_s = self.submission_id is not None
        has_d = self.draft_client_id is not None
        if has_s and has_d:
            raise ValueError("Provide only one of submission_id or draft_client_id")
        if not has_s and not has_d:
            raise ValueError("Provide exactly one of submission_id or draft_client_id")
        return self


class PresignedUploadData(BaseModel):
    """Response payload containing upload target information."""

    upload_url: str
    url: str
    expires_in: int
    original_url: str | None = Field(
        default=None,
        description="Public URL of the original object (property images only).",
    )
    upload_completed: bool = Field(
        default=False,
        description=(
            "When true, the server already stored the file (watermarked). "
            "Do not perform a client PUT to upload_url."
        ),
    )
    requires_watermark_finalize: bool = Field(
        default=False,
        description="Deprecated; not used for property images.",
    )


class PropertyImageFinalizeRequest(BaseModel):
    """Apply watermark to an image already uploaded via presigned PUT (same S3 key)."""

    submission_id: uuid.UUID | None = None
    draft_client_id: uuid.UUID | None = None
    file_name: str

    @model_validator(mode="after")
    def exactly_one_draft_key(self) -> Self:
        has_s = self.submission_id is not None
        has_d = self.draft_client_id is not None
        if has_s and has_d:
            raise ValueError("Provide only one of submission_id or draft_client_id")
        if not has_s and not has_d:
            raise ValueError("Provide exactly one of submission_id or draft_client_id")
        return self


class PropertyImageUploadData(BaseModel):
    """Response payload after server-side watermarked property image upload."""

    url: str
    file_name: str
    original_url: str | None = Field(
        default=None,
        description="Public URL of the preserved original upload.",
    )

