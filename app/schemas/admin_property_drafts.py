"""Schemas for admin draft property submissions (wizard drafts)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AdminDraftSubmissionItem(BaseModel):
    """In-progress wizard (no normalized property row yet), for admin."""

    submission_id: uuid.UUID
    status: str
    current_step: int
    last_completed_step: int
    title: str | None = Field(default=None, description="From payload.basic_information.title when present")
    updated_at: datetime
    can_edit: bool = True
    can_delete: bool = True


class AdminDraftSubmissionListResponse(BaseModel):
    items: list[AdminDraftSubmissionItem]
    total: int
    page: int
    limit: int

