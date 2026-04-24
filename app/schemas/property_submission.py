"""Pydantic schemas for property listing submission workflow."""

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


SubmissionStep = Literal[
    "basic_information",
    "location",
    "owner_information",
    "property_details",
    "pricing",
    "amenities",
    "media_documents",
    "review_submit",
]

SubmissionAction = Literal["save", "next", "previous", "save_draft"]


DEFAULT_STEP_COMPLETION: dict[str, bool] = {
    "basic_information": False,
    "location": False,
    "owner_information": False,
    "property_details": False,
    "pricing": False,
    "amenities": False,
    "media_documents": False,
    "review_submit": False,
}

DEFAULT_SUBMISSION_PAYLOAD: dict[str, Any] = {
    "basic_information": {},
    "location": {},
    "owner_information": {"owners": []},
    "property_details": {},
    "pricing": {},
    "amenities": {"feature_ids": []},
    "media_documents": {
        "images": [],
        "videos": [],
        "documents": [],
        "youtube_url": None,
        "virtual_tour_url": None,
    },
    "review_submit": {},
}

STEP_ORDER: list[SubmissionStep] = [
    "basic_information",
    "location",
    "owner_information",
    "property_details",
    "pricing",
    "amenities",
    "media_documents",
    "review_submit",
]
STEP_INDEX: dict[SubmissionStep, int] = {step: idx + 1 for idx, step in enumerate(STEP_ORDER)}


class SubmissionFileMetadata(BaseModel):
    """Reusable metadata shape for owner/media/document references."""

    url: str
    file_name: str
    caption: str | None = None
    display_order: int | None = None
    is_primary: bool | None = None


class CreatePropertySubmissionRequest(BaseModel):
    """Optional prefill values for draft creation."""

    payload: dict[str, Any] | None = None


class PropertySubmissionCreateResponse(BaseModel):
    submission_id: uuid.UUID
    status: str
    current_step: int
    last_completed_step: int
    step_completion: dict[str, bool]


class PropertySubmissionDetailResponse(PropertySubmissionCreateResponse):
    payload: dict[str, Any]


class PropertySubmissionPatchRequest(BaseModel):
    step: SubmissionStep
    action: SubmissionAction = "save"
    data: dict[str, Any] = Field(default_factory=dict)


class PropertySubmissionPatchResponse(BaseModel):
    submission_id: uuid.UUID
    status: str
    current_step: int
    last_completed_step: int
    saved_step: SubmissionStep
    step_completion: dict[str, bool]
    payload: dict[str, Any] = Field(
        ...,
        description="Merged submission payload after save (same keys as GET). Use to sync client state without a second GET.",
    )


class PropertySubmissionSubmitRequest(BaseModel):
    confirm_submit: bool


class PropertySubmissionSubmitResponse(BaseModel):
    submission_id: uuid.UUID
    property_id: uuid.UUID
    status: str


AdminReviewAction = Literal["approve", "changes_requested", "reject"]


class AdminSubmissionListItem(BaseModel):
    submission_id: uuid.UUID
    submitted_by: uuid.UUID
    status: str
    property_id: uuid.UUID | None = None
    current_step: int
    submitted_at: str | None = None
    reviewed_at: str | None = None


class AdminSubmissionListResponse(BaseModel):
    items: list[AdminSubmissionListItem]
    page: int
    limit: int
    total: int


class AdminSubmissionDetailResponse(BaseModel):
    submission_id: uuid.UUID
    status: str
    property_id: uuid.UUID | None = None
    submitted_by: uuid.UUID
    submitted_at: str | None = None
    reviewed_by: uuid.UUID | None = None
    reviewed_at: str | None = None
    review_reason: str | None = None
    payload: dict[str, Any]


class AdminSubmissionReviewRequest(BaseModel):
    action: AdminReviewAction
    reason: str | None = None


class AdminSubmissionReviewResponse(BaseModel):
    submission_id: uuid.UUID
    status: str
    reviewed_by: uuid.UUID | None = None
    reviewed_at: str | None = None
    review_reason: str | None = None
