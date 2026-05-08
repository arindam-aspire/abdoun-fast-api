"""Pydantic schemas for lead lifecycle APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class ContactFormLeadCreateRequest(BaseModel):
    propertyId: str
    name: str = Field(min_length=2, max_length=20)
    email: str = Field(min_length=5, max_length=255)
    phoneNumber: str = Field(min_length=8, max_length=20)
    message: str = Field(min_length=10, max_length=1000)


class ManualOwnerLeadCreateRequest(BaseModel):
    ownerName: str = Field(min_length=1, max_length=255)
    phoneNumber: Optional[str] = Field(default=None, min_length=7, max_length=50)
    email: Optional[EmailStr] = None
    message: str = Field(min_length=1, max_length=1000)
    relatedPropertyName: str = Field(min_length=1, max_length=255)

    @field_validator("ownerName", "message", "relatedPropertyName")
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Field is required")
        return value

    @field_validator("phoneNumber")
    @classmethod
    def normalize_phone(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value else None

    @model_validator(mode="after")
    def require_contact_method(self) -> "ManualOwnerLeadCreateRequest":
        if not self.phoneNumber and not self.email:
            raise ValueError("At least one contact method is required: phoneNumber or email")
        return self


class AdminManualLeadCreateRequest(BaseModel):
    propertyId: UUID
    assignedAgentId: UUID
    source: str = Field(pattern="^(PHONE|WHATSAPP|MANUAL_ADMIN)$")
    message: str = Field(min_length=10, max_length=1000)
    contactUserId: Optional[UUID] = None


class PropertySummaryResponse(BaseModel):
    id: str
    title: Optional[str] = None
    slug: Optional[str] = None
    thumbnailUrl: Optional[str] = None
    propertyHash: Optional[int] = Field(
        default=None,
        description="Numeric public property id (properties_normalized.property_hash); use for FE routes like /property-details/{propertyHash}.",
    )


class AssignedAgentSummaryResponse(BaseModel):
    id: str
    fullName: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class LeadUserSummaryResponse(BaseModel):
    id: str
    fullName: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class ExternalOwnerSummaryResponse(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class LeadStatusUpdateRequest(BaseModel):
    status: str = Field(pattern="^(NEW|IN_PROGRESS|REQUEST_FOR_CLOSE|CLOSED)$")
    reason: Optional[str] = Field(default=None, max_length=500)


class LeadReassignRequest(BaseModel):
    assignedAgentId: UUID


class LeadReplyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class LeadNoteCreateRequest(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


class LeadNoteUpdateRequest(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


class LeadItemResponse(BaseModel):
    id: UUID
    leadNumber: str
    propertyId: Optional[UUID] = None
    property: Optional[PropertySummaryResponse] = None
    userId: Optional[UUID] = None
    user: Optional[LeadUserSummaryResponse] = None
    communicationMode: Optional[str] = None
    externalOwner: Optional[ExternalOwnerSummaryResponse] = None
    externalPropertyName: Optional[str] = None
    createdByAgentId: Optional[UUID] = None
    status: str
    source: str
    assignedAgentId: Optional[UUID] = None
    assignedAgent: Optional[AssignedAgentSummaryResponse] = None
    assignedByAdminId: Optional[UUID] = None
    message: Optional[str] = None
    lastActivityAt: Optional[datetime] = None
    requestCloseAt: Optional[datetime] = None
    closedAt: Optional[datetime] = None
    closedByAdminId: Optional[UUID] = None
    createdAt: datetime
    updatedAt: datetime


class LeadListResponse(BaseModel):
    items: list[LeadItemResponse]
    total: int
    page: int
    pageSize: int


class LeadNoteResponse(BaseModel):
    id: UUID
    leadId: UUID
    authorUserId: Optional[UUID] = None
    note: str
    createdAt: datetime
    updatedAt: datetime


class LeadNotesResponse(BaseModel):
    items: list[LeadNoteResponse]


class LeadReplyResponse(BaseModel):
    id: UUID
    leadId: UUID
    senderUserId: Optional[UUID] = None
    recipientUserId: Optional[UUID] = None
    message: str
    channel: str
    deliveryState: Optional[str] = None
    createdAt: datetime


class LeadMessagesResponse(BaseModel):
    items: list[LeadReplyResponse]


class LeadHistoryItemResponse(BaseModel):
    id: UUID
    leadId: UUID
    fromStatus: Optional[str] = None
    toStatus: str
    actorUserId: Optional[UUID] = None
    actorRole: Optional[str] = None
    reason: Optional[str] = None
    changedAt: datetime


class LeadHistoryResponse(BaseModel):
    items: list[LeadHistoryItemResponse]
