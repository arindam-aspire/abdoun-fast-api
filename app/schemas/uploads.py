from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


UploadContext = Literal[
    "owner_document",
    "property_media_image",
    "property_document",
    "agency_legal_document",
]


class PresignedUploadRequest(BaseModel):
    file_name: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    file_size: int = Field(ge=0)
    context: UploadContext
    draft_client_id: str | None = None
    submission_id: str | None = None
