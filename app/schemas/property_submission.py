"""Pydantic schemas for property listing submission workflow."""

import uuid
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, model_validator


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
    """Create or replace a **server draft**.

    **Recommended (new app flow):** send ``payload`` with the full stepper state when the user saves a draft
    (Redux-first: no server round-trip on “Add property” alone).

    **Backward compatible:** omit the body or omit ``payload`` to create an **empty** draft row (legacy clients);
    the new UI does not need to call this empty variant on entry.
    """

    payload: dict[str, Any] | None = None
    current_step: int = Field(1, ge=1, le=8, description="Active step when saving the draft (default 1).")


class PropertySubmissionCreateResponse(BaseModel):
    submission_id: uuid.UUID
    status: str
    current_step: int
    last_completed_step: int
    step_completion: dict[str, bool]
    payload: dict[str, Any] | None = Field(
        default=None,
        description="When the client sent a full ``payload`` on create, the stored merged payload; otherwise null for empty create.",
    )


class CreateAndSubmitPropertySubmissionRequest(BaseModel):
    """Create submission, validate, and persist the property in one request (Redux-first / no prior submission id)."""

    payload: dict[str, Any]
    confirm_submit: bool


class PropertySubmissionDetailResponse(PropertySubmissionCreateResponse):
    payload: dict[str, Any]
    reviewed_by: uuid.UUID | None = None
    reviewed_at: str | None = None
    review_reason: str | None = None


class PropertySubmissionPatchRequest(BaseModel):
    """Patch a single step (``step`` + ``data``) or replace the whole draft (``payload`` + ``action=save_draft``)."""

    step: SubmissionStep | None = None
    action: SubmissionAction = "save"
    data: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] | None = None
    current_step: int | None = Field(
        default=None,
        ge=1,
        le=8,
        description="Set when sending full ``payload``; active wizard step after save (default 1).",
    )

    @model_validator(mode="after")
    def full_payload_vs_step(self) -> Self:
        if self.payload is not None:
            if self.action != "save_draft":
                raise ValueError("When 'payload' is set, 'action' must be 'save_draft' (full draft save on existing id)")
            if self.step is not None:
                raise ValueError("Omit 'step' when sending full 'payload' (use 'current_step' instead)")
            if self.data:
                raise ValueError("Omit 'data' when sending full 'payload'")
            if self.current_step is None:
                self.current_step = 1
        else:
            if self.step is None:
                raise ValueError("Field required: 'step' (or send 'payload' with 'action' save_draft to save the full form)")
        return self


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


class AdminPropertySubmissionSubmitExistingRequest(BaseModel):
    """Admin submits an existing draft submission by id (auto-approves)."""

    confirm_submit: bool


class PropertySubmissionSubmitResponse(BaseModel):
    submission_id: uuid.UUID
    property_id: uuid.UUID
    status: str


class PropertySubmissionDeleteResponse(BaseModel):
    submission_id: uuid.UUID
    property_id: uuid.UUID | None = Field(
        default=None,
        description="Normalized property id if one was removed; null when the draft had no property row yet.",
    )
    status: str | None = Field(default=None, description="Action result status (e.g. deleted).")
    deleted_at: str | None = Field(default=None, description="ISO timestamp when soft delete occurred.")


AdminReviewAction = Literal["approve", "changes_requested", "reject"]


class AdminSubmissionListItem(BaseModel):
    submission_id: uuid.UUID
    submitted_by: uuid.UUID
    submitted_by_name: str | None = None
    status: str
    property_id: uuid.UUID | None = None
    agent_user_id: uuid.UUID | None = Field(
        default=None,
        description="Explicit assigned agent for the property (properties_normalized.agent_user_id). Null means unassigned.",
    )
    has_assigned_agent: bool = Field(
        default=False,
        description="Convenience flag derived from agent_user_id; true when an agent is explicitly assigned.",
    )
    property_hash: int | None = Field(
        default=None,
        description="Numeric property id used by GET /api/v1/properties/{property_id} (same as properties_normalized.property_hash).",
    )
    property_title: str | None = None
    property_reference_number: str | None = None
    current_step: int
    submitted_at: str | None = None
    reviewed_at: str | None = None


class AdminSubmissionListResponse(BaseModel):
    """Admin submission list with pagination."""

    items: list[AdminSubmissionListItem]
    page: int
    total: int
    pageSize: int
    totalPages: int
    hasNext: bool
    hasPrevious: bool


class AdminSubmissionDetailResponse(BaseModel):
    submission_id: uuid.UUID
    status: str
    property_id: uuid.UUID | None = None
    property_hash: int | None = Field(
        default=None,
        description="Numeric property id used by GET /api/v1/properties/{property_id} (same as properties_normalized.property_hash).",
    )
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
