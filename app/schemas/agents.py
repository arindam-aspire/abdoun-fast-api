from __future__ import annotations

from pydantic import BaseModel


class AgentInviteRequest(BaseModel):
    email: str
    full_name: str | None = None
    phone_number: str | None = None
    service_area: str | None = None


class AgentReviewRequest(BaseModel):
    status: str
    reason: str | None = None


class AgentStatusUpdateRequest(BaseModel):
    status: str
    reason: str | None = None
