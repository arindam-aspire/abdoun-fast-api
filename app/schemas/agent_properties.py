"""Schemas for authenticated agent / creator property list (dashboard)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class AgentPropertyAgencyInfo(BaseModel):
    agency_id: str
    agency_name: str | None = None
    agency_trade_name: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None


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
    submission_workflow_label: str | None = Field(
        default=None,
        description="Stable key for agent UX: e.g. pending_admin_approval, verified (when workflow approved), rejected. Distinct from catalog `status_slug` (Verified).",
    )
    can_edit_submission: bool = False
    can_delete_submission: bool = False
    agency: AgentPropertyAgencyInfo | None = None


class AgentDraftSubmissionItem(BaseModel):
    """In-progress wizard (no normalized property row yet)."""

    submission_id: uuid.UUID
    status: str
    current_step: int
    last_completed_step: int
    title: str | None = Field(default=None, description="From payload.basic_information.title when present")
    updated_at: datetime
    can_edit: bool = True
    can_delete: bool = True


class AgentPropertyListResponse(BaseModel):
    """Paginated list of properties created by the current user."""

    items: list[AgentPropertyListItem]
    total: int
    page: int
    pageSize: int
    totalPages: int
    hasNext: bool
    hasPrevious: bool
    # Only included when `include_drafts=true` on the endpoint.
    draft_submissions: list[AgentDraftSubmissionItem] | None = Field(
        default=None,
        description="Draft / in_progress submissions without property_id (same submitter)",
    )
    draft_submissions_total: int | None = None


class AgentDraftSubmissionListResponse(BaseModel):
    """Draft-only listing for the agent dashboard (no normalized property row yet)."""

    items: list[AgentDraftSubmissionItem]
    total: int
    page: int
    pageSize: int
    totalPages: int
    hasNext: bool
    hasPrevious: bool
