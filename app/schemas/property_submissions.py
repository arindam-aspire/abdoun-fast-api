from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class PropertySubmissionCreateRequest(BaseModel):
    agency_id: UUID | None = None
    payload: dict[str, Any]
    current_step: int = 1
    last_completed_step: int = 0


class PropertySubmissionUpdateRequest(BaseModel):
    action: Literal["save_draft"] = "save_draft"
    agency_id: UUID | None = None
    current_step: int
    last_completed_step: int
    payload: dict[str, Any]


class PropertySubmissionDirectSubmitRequest(BaseModel):
    agency_id: UUID | None = None
    payload: dict[str, Any]
    confirm_submit: bool


class PropertySubmissionSubmitRequest(BaseModel):
    confirm_submit: bool


class PropertySubmissionReviewRequest(BaseModel):
    action: Literal["approve", "reject"]
    reason: str | None = None


class PropertyAssignAgentRequest(BaseModel):
    agent_id: str | None = None
