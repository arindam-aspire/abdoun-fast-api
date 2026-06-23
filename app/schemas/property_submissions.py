from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class PropertySubmissionCreateRequest(BaseModel):
    payload: dict[str, Any]
    current_step: int = 1
    last_completed_step: int = 0


class PropertySubmissionUpdateRequest(BaseModel):
    action: Literal["save_draft"] = "save_draft"
    current_step: int
    last_completed_step: int
    payload: dict[str, Any]


class PropertySubmissionDirectSubmitRequest(BaseModel):
    payload: dict[str, Any]
    confirm_submit: bool


class PropertySubmissionSubmitRequest(BaseModel):
    confirm_submit: bool


class PropertySubmissionReviewRequest(BaseModel):
    action: Literal["approve", "reject"]
    reason: str | None = None


class PropertyAssignAgentRequest(BaseModel):
    agent_id: str | None = None
