"""Pydantic schemas for lead lifecycle APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class ContactFormLeadCreateRequest(BaseModel):
    propertyId: str
    name: str = Field(min_length=2, max_length=20)
    email: str = Field(min_length=5, max_length=255)
    phoneNumber: str = Field(min_length=8, max_length=20)
    message: str = Field(min_length=10, max_length=1000)


class OfflineLeadCreateRequest(BaseModel):
    customerName: str = Field(min_length=1, max_length=255)
    phoneNumber: str = Field(min_length=7, max_length=50)
    propertyName: Optional[str] = Field(default=None, max_length=255)
    propertyId: Optional[UUID] = None
    inquiryType: str = Field(pattern="^(BUY|RENT|SELL|OTHER)$")
    source: str = Field(pattern="^(PHONE|WHATSAPP|WALK_IN|FACEBOOK|REFERRAL|OTHER)$")
    notes: Optional[str] = Field(default=None, max_length=2000)
    assignedAgentId: Optional[UUID] = None

    @field_validator("customerName")
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Field is required")
        return value

    @field_validator("propertyName", "notes")
    @classmethod
    def normalize_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("phoneNumber")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        value = value.strip()
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) < 7:
            raise ValueError("Invalid phone number")
        return value

    @model_validator(mode="after")
    def require_property_reference(self) -> "OfflineLeadCreateRequest":
        if not self.propertyId and not self.propertyName:
            raise ValueError("Either propertyName or propertyId is required")
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


class OfflineLeadSummaryResponse(BaseModel):
    customerName: Optional[str] = None
    phoneNumber: Optional[str] = None
    propertyName: Optional[str] = None
    propertyId: Optional[str] = None
    inquiryType: Optional[str] = None
    source: Optional[str] = None
    notes: Optional[str] = None
    createdByAgentId: Optional[str] = None
    createdByAdminId: Optional[str] = None


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
    createdByAdminId: Optional[UUID] = None
    offlineLead: Optional[OfflineLeadSummaryResponse] = None
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


class LeadStatusSummaryResponse(BaseModel):
    total: int = 0
    NEW: int = 0
    IN_PROGRESS: int = 0
    REQUEST_FOR_CLOSE: int = 0
    CLOSED: int = 0


class LeadListResponse(BaseModel):
    items: list[LeadItemResponse]
    total: int
    page: int
    pageSize: int
    summary: LeadStatusSummaryResponse


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
