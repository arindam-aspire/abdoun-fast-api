"""Schemas for authenticated agent / creator property list (dashboard)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class AgentPropertyListItem(BaseModel):
    """One row for manage-listings table (normalized property)."""

    property_id: uuid.UUID
    property_hash: int = Field(description="Stable numeric handle derived from UUID")
    title: str
    listing_purpose: str | None = None
    type_name: str | None = None
    type_slug: str | None = None
    category_name: str | None = None
    category_slug: str | None = None
    status_name: str | None = None
    status_slug: str | None = None
    price: Decimal
    currency: str | None = None
    reference_number: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    submission_id: uuid.UUID | None = Field(
        default=None,
        description="Linked property_listing_submissions row when this property came from the stepper",
    )
    submission_status: str | None = Field(
        default=None,
        description="Workflow status: draft, in_progress, submitted, changes_requested, approved, rejected",
    )
    submission_submitted_at: datetime | None = None
    submission_reviewed_at: datetime | None = None
    submission_review_reason: str | None = None


class AgentDraftSubmissionItem(BaseModel):
    """In-progress wizard (no normalized property row yet)."""

    submission_id: uuid.UUID
    status: str
    current_step: int
    last_completed_step: int
    title: str | None = Field(default=None, description="From payload.basic_information.title when present")
    updated_at: datetime


class AgentPropertyListResponse(BaseModel):
    """Paginated list of properties created by the current user."""

    items: list[AgentPropertyListItem]
    total: int
    page: int
    limit: int
    draft_submissions: list[AgentDraftSubmissionItem] = Field(
        default_factory=list,
        description="Draft / in_progress submissions without property_id (same submitter)",
    )
    draft_submissions_total: int = 0
