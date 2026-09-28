from __future__ import annotations

from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.schemas.agents import normalize_phone, validate_e164_phone


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
    model_config = ConfigDict(populate_by_name=True)

    agency_name: str
    agency_trade_name: str
    email: str
    phone: str
    legal_document_s3_link: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "legal_document_s3_link",
            "legalDocumentS3Link",
            "document_url",
            "documentUrl",
            "licence_url",
            "license_url",
        ),
    )
    website: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    zip_code: str | None = None
    currency: str | None = None
    measurement_unit: str | None = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        return validate_e164_phone(value, field_name="phone")

    @field_validator("legal_document_s3_link")
    @classmethod
    def blank_document_to_none(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return value.strip()


class AgencyInvitationCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    email: str
    agency_name: str | None = None
    agency_trade_name: str | None = None
    phone: str | None = Field(
        default=None,
        validation_alias=AliasChoices("phone", "phone_number", "phoneNumber"),
    )
    legal_document_s3_link: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "legal_document_s3_link",
            "legalDocumentS3Link",
            "document_url",
            "documentUrl",
            "licence_url",
            "license_url",
        ),
    )

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return validate_e164_phone(value, field_name="phone")

    @field_validator("legal_document_s3_link")
    @classmethod
    def blank_document_to_none(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return value.strip()


class AgencyInvitationAcceptRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    token: str
    agency_name: str
    agency_trade_name: str
    phone: str = Field(validation_alias=AliasChoices("phone", "phone_number", "phoneNumber"))
    legal_document_s3_link: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "legal_document_s3_link",
            "legalDocumentS3Link",
            "document_url",
            "documentUrl",
            "licence_url",
            "license_url",
        ),
    )
    website: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    zip_code: str | None = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        return validate_e164_phone(value, field_name="phone")

    @field_validator("legal_document_s3_link")
    @classmethod
    def blank_document_to_none(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return value.strip()


class AgencyReviewRequest(BaseModel):
    action: str
    reason: str | None = None


class AgencyActivationRequest(BaseModel):
    is_active: bool


class AgencyPasswordSetupRequest(BaseModel):
    token: str
    password: str


class OwnerAgencyAssignmentRequest(BaseModel):
    agency_id: UUID


class UploadRequest(BaseModel):
    file_name: str
    content_type: str
    file_size: int
