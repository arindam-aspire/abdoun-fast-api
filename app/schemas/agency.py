"""Pydantic schemas for agency registration and management."""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Optional

from pydantic import AliasChoices, BaseModel, EmailStr, Field, HttpUrl, field_validator, model_validator

from app.schemas.user import UserResponse
from app.utils.constants import Defaults, ValidationMessages
PHONE_E164_REGEX = r"^\+[1-9]\d{7,14}$"
CURRENCY_ISO_REGEX = re.compile(r"^[A-Za-z]{3}$")
MEASUREMENT_UNIT_ALLOWED = frozenset({"sqm", "sqft", "acre", "hectare"})


def _validate_currency(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip().upper()
    if not CURRENCY_ISO_REGEX.match(cleaned):
        raise ValueError("currency must be a 3-letter ISO 4217 code (e.g. JOD, USD)")
    return cleaned


def _validate_measurement_unit(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip().lower()
    if cleaned not in MEASUREMENT_UNIT_ALLOWED:
        allowed = ", ".join(sorted(MEASUREMENT_UNIT_ALLOWED))
        raise ValueError(f"measurement_unit must be one of: {allowed}")
    return cleaned


def _validate_password_strength(value: str) -> str:
    if len(value) < Defaults.PASSWORD_MIN_LENGTH:
        raise ValueError(ValidationMessages.PASSWORD_MIN_LENGTH)
    if not any(c.isupper() for c in value):
        raise ValueError(ValidationMessages.PASSWORD_UPPERCASE)
    if not any(c.islower() for c in value):
        raise ValueError(ValidationMessages.PASSWORD_LOWERCASE)
    if not any(c.isdigit() for c in value):
        raise ValueError(ValidationMessages.PASSWORD_NUMBER)
    if not any(c in ValidationMessages.PASSWORD_SPECIAL_CHARS for c in value):
        raise ValueError(ValidationMessages.PASSWORD_SPECIAL)
    return value


class AgencyBase(BaseModel):
    email: EmailStr
    phone_number: str = Field(
        ...,
        validation_alias=AliasChoices("phone_number", "phone"),
    )
    agency_name: str = Field(..., min_length=1, max_length=255)
    agency_trade_name: str = Field(..., min_length=1, max_length=255)
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    zip_code: Optional[str] = Field(
        None,
        max_length=20,
        validation_alias=AliasChoices("zip_code", "zipcode"),
    )
    website: Optional[HttpUrl] = None
    currency: Optional[str] = Field(
        None,
        max_length=3,
        description="ISO 4217 currency code (defaults to JOD on registration).",
    )
    measurement_unit: Optional[str] = Field(
        None,
        max_length=20,
        description="Agency preferred area unit (defaults to sqm on registration).",
    )

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: Optional[str]) -> Optional[str]:
        return _validate_currency(value)

    @field_validator("measurement_unit")
    @classmethod
    def validate_measurement_unit(cls, value: Optional[str]) -> Optional[str]:
        return _validate_measurement_unit(value)

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str) -> str:
        phone = value.strip()
        if not re.match(PHONE_E164_REGEX, phone):
            raise ValueError(ValidationMessages.PHONE_E164)
        return phone

    @field_validator("agency_name", "agency_trade_name")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field cannot be empty")
        return cleaned


class AgencyRegisterRequest(AgencyBase):
    """JSON registration: presigned PUT upload (same pattern as POST /auth/me/profile-picture)."""

    file_name: str = Field(..., min_length=1)
    content_type: str = Field(..., min_length=1)
    file_size: Optional[int] = Field(None, gt=0)
    password: str = Field(..., min_length=Defaults.PASSWORD_MIN_LENGTH)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password_strength(value)


class AgencyRegisterMultipartRequest(AgencyBase):
    password: str = Field(..., min_length=Defaults.PASSWORD_MIN_LENGTH)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password_strength(value)


class AgencyUpdateRequest(BaseModel):
    agency_name: Optional[str] = Field(None, min_length=1, max_length=255)
    agency_trade_name: Optional[str] = Field(None, min_length=1, max_length=255)
    legal_document_file_name: Optional[str] = Field(None, min_length=1)
    legal_document_content_type: Optional[str] = Field(None, min_length=1)
    legal_document_file_size: Optional[int] = Field(None, gt=0)
    phone: Optional[str] = None
    website: Optional[HttpUrl] = None
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    zip_code: Optional[str] = Field(
        None,
        max_length=20,
        validation_alias=AliasChoices("zip_code", "zipcode"),
    )
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
    currency: Optional[str] = Field(None, max_length=3)
    measurement_unit: Optional[str] = Field(None, max_length=20)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: Optional[str]) -> Optional[str]:
        return _validate_currency(value)

    @field_validator("measurement_unit")
    @classmethod
    def validate_measurement_unit(cls, value: Optional[str]) -> Optional[str]:
        return _validate_measurement_unit(value)

    @field_validator(
        "agency_name",
        "agency_trade_name",
        "legal_document_file_name",
        "legal_document_content_type",
        "phone",
        "address",
        "city",
        "state",
        "country",
        "zip_code",
        "currency",
        "measurement_unit",
        mode="before",
    )
    @classmethod
    def empty_string_as_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        phone = value.strip()
        if not re.match(PHONE_E164_REGEX, phone):
            raise ValueError(ValidationMessages.PHONE_E164)
        return phone

    @model_validator(mode="after")
    def validate_legal_document_presign_fields(self) -> "AgencyUpdateRequest":
        has_name = bool((self.legal_document_file_name or "").strip())
        has_ct = bool((self.legal_document_content_type or "").strip())
        if has_name and not has_ct:
            raise ValueError("legal_document_content_type is required when legal_document_file_name is set")
        if has_ct and not has_name:
            raise ValueError("legal_document_file_name is required when legal_document_content_type is set")
        return self


class AgencyResponse(BaseModel):
    id: uuid.UUID
    agency_name: str
    agency_trade_name: str
    legal_document_s3_link: str
    logo_url: Optional[str] = None
    email: EmailStr
    phone: str
    profile_picture_url: str = None
    website: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    zip_code: Optional[str] = None
    currency: str
    measurement_unit: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgencyLegalDocumentUploadData(BaseModel):
    """Presigned PUT metadata returned after registration or upload initiation."""

    legal_document_s3_link: str
    upload_url: str
    expires_in: int


class AgencyRegisterResponse(BaseModel):
    agency: AgencyResponse
    user: UserResponse
    legal_document_upload: Optional[AgencyLegalDocumentUploadData] = None


class AgencyDocumentUploadRequest(BaseModel):
    file_name: str = Field(..., min_length=1)
    content_type: str = Field(..., min_length=1)
    file_size: Optional[int] = Field(None, gt=0)


class AgencyDocumentUploadResponse(BaseModel):
    upload_url: str
    legal_document_s3_link: str
    expires_in: int


class AgencyUpdateResult(BaseModel):
    agency: AgencyResponse
    legal_document_upload: Optional[AgencyLegalDocumentUploadData] = None


class AgencyLogoUploadRequest(BaseModel):
    file_name: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("file_name", "fileName", "filename", "name"),
    )
    content_type: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("content_type", "contentType", "mime_type", "mimeType"),
    )
    file_size: Optional[int] = Field(
        None,
        gt=0,
        validation_alias=AliasChoices("file_size", "fileSize", "size"),
    )

    model_config = {"populate_by_name": True}


class AgencyLogoUploadResponse(BaseModel):
    """``logo_url`` is presigned GET in API responses; ``upload_url`` is presigned PUT for client upload."""

    logo_url: str
    upload_url: str
    expires_in: int


class AgencyLogoGetResponse(BaseModel):
    logo_url: str
    expires_in: int
