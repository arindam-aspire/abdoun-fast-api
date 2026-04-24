"""Schemas for upload helper endpoints."""

import uuid
from typing import Literal

from pydantic import BaseModel


UploadContext = Literal[
    "owner_document",
    "property_media_image",
    "property_media_video",
    "property_document",
]


class PresignedUploadRequest(BaseModel):
    """Request payload for generating a presigned upload URL."""

    submission_id: uuid.UUID
    context: UploadContext
    file_name: str
    content_type: str
    file_size: int | None = None


class PresignedUploadData(BaseModel):
    """Response payload containing upload target information."""

    upload_url: str
    url: str
    expires_in: int

