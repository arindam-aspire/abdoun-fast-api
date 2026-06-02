"""Pydantic schemas for agency registration and management."""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Optional

from pydantic import AliasChoices, BaseModel, EmailStr, Field, HttpUrl, field_validator

from app.schemas.user import UserResponse
from app.utils.constants import Defaults, ValidationMessages


PHONE_E164_REGEX = r"^\+[1-9]\d{7,14}$"


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
    legal_document_s3_link: str = Field(..., min_length=1)
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
    legal_document_s3_link: Optional[str] = Field(None, min_length=1)
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

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        phone = value.strip()
        if not re.match(PHONE_E164_REGEX, phone):
            raise ValueError(ValidationMessages.PHONE_E164)
        return phone


class AgencyResponse(BaseModel):
    id: uuid.UUID
    agency_name: str
    agency_trade_name: str
    legal_document_s3_link: str
    email: EmailStr
    phone: str
    website: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    zip_code: Optional[str] = None
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgencyRegisterResponse(BaseModel):
    agency: AgencyResponse
    user: UserResponse


class AgencyDocumentUploadRequest(BaseModel):
    file_name: str = Field(..., min_length=1)
    content_type: str = Field(..., min_length=1)
    file_size: Optional[int] = Field(None, gt=0)


class AgencyDocumentUploadResponse(BaseModel):
    upload_url: str
    legal_document_s3_link: str
    expires_in: int
