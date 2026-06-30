from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


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


class AgentInvitationAcceptRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


class ManualOnboardAgentRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    full_name: str = Field(validation_alias=AliasChoices("fullName", "full_name"))
    email: str
    phone: str | None = None
    service_area: str | None = Field(default=None, validation_alias=AliasChoices("serviceArea", "service_area"))
