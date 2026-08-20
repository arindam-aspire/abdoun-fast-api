from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


UploadContext = Literal[
    "owner_document",
    "property_media_image",
    "property_document",
    "agency_legal_document",
    "agent_identity_document",
]


class PresignedUploadRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    file_name: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    file_size: int = Field(ge=0)
    context: UploadContext
    draft_client_id: str | None = None
    submission_id: str | None = None
    agency_id: UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("agencyId", "agency_id"),
    )


class ReadableUrlRequest(BaseModel):
    file_url: str = Field(min_length=1)
