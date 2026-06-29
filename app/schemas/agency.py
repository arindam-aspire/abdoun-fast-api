from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class AgencyUpdateRequest(BaseModel):
    agency_name: str | None = None
    agency_trade_name: str | None = None
    website: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    zip_code: str | None = None
    currency: str | None = None
    measurement_unit: str | None = None


class AgencyOfflineRegistrationRequest(BaseModel):
    agency_name: str
    agency_trade_name: str
    email: str
    phone: str
    legal_document_s3_link: str | None = None
    website: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    zip_code: str | None = None
    currency: str | None = None
    measurement_unit: str | None = None


class AgencyInvitationCreateRequest(BaseModel):
    email: str
    agency_name: str | None = None
    agency_trade_name: str | None = None
    phone: str | None = None


class AgencyInvitationAcceptRequest(BaseModel):
    token: str
    agency_name: str
    agency_trade_name: str
    phone: str
    legal_document_s3_link: str | None = None
    website: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    zip_code: str | None = None


class AgencyReviewRequest(BaseModel):
    action: str
    reason: str | None = None


class AgencyPasswordSetupRequest(BaseModel):
    token: str
    password: str


class OwnerAgencyAssignmentRequest(BaseModel):
    agency_id: UUID


class UploadRequest(BaseModel):
    file_name: str
    content_type: str
    file_size: int
