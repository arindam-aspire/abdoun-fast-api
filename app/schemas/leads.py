from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


LeadSource = Literal["EMAIL_FORM", "PHONE", "WHATSAPP", "MANUAL_ADMIN", "AGENT_MANUAL", "OFFLINE_MANUAL"]
LeadStatus = Literal["NEW", "IN_PROGRESS", "REQUEST_FOR_CLOSE", "CLOSED"]
LeadMessageChannel = Literal["IN_APP", "EMAIL", "SMS"]


class LeadCreate(BaseModel):
    property_hash: int | str
    inquiry_type: str | None = Field(default="general", max_length=50)
    message: str | None = None
    source: LeadSource = "EMAIL_FORM"
    communication_mode: str = "IN_APP"
    contact_name: str | None = Field(default=None, max_length=255)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=50)


class LeadAssignRequest(BaseModel):
    agent_id: UUID | None


class LeadStatusUpdateRequest(BaseModel):
    status: LeadStatus
    reason: str | None = None


class LeadCloseRequest(BaseModel):
    reason: str | None = None


class LeadCloseRequestDecision(BaseModel):
    reason: str | None = None


class LeadNoteCreate(BaseModel):
    note: str = Field(min_length=1)


class LeadMessageCreate(BaseModel):
    message: str = Field(min_length=1)
    channel: LeadMessageChannel = "IN_APP"
    recipient_user_id: UUID | None = None
