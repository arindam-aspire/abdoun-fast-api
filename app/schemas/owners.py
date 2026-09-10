from __future__ import annotations

import re

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, field_validator


PHONE_E164_REGEX = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_phone(value: str) -> str:
    cleaned = re.sub(r"[\s\-()]", "", (value or "").strip())
    if cleaned and not cleaned.startswith("+") and cleaned.isdigit():
        cleaned = f"+{cleaned}"
    return cleaned


class OwnerCreateRequest(BaseModel):
    """Create an owner that can be selected in the Add Property workflow."""

    model_config = ConfigDict(populate_by_name=True)

    full_name: str = Field(min_length=1, max_length=255, validation_alias=AliasChoices("fullName", "full_name"))
    email: EmailStr
    phone_number: str | None = Field(
        default=None,
        validation_alias=AliasChoices("phoneNumber", "phone_number", "phone"),
    )

    @field_validator("full_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("phone_number")
    @classmethod
    def validate_optional_phone(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        normalized = normalize_phone(value)
        if not PHONE_E164_REGEX.match(normalized):
            raise ValueError("phone_number must include country code in E.164 format (e.g. +9627xxxxxxx)")
        return normalized


class OwnerUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    full_name: str | None = Field(default=None, validation_alias=AliasChoices("fullName", "full_name"))
    email: str | None = None
    phone_number: str | None = Field(
        default=None,
        validation_alias=AliasChoices("phoneNumber", "phone_number", "phone"),
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lower()
        return cleaned or None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not str(value).strip():
            return ""
        normalized = normalize_phone(value)
        if not PHONE_E164_REGEX.match(normalized):
            raise ValueError("phone_number must include country code in E.164 format (e.g. +9627xxxxxxx)")
        return normalized


class OwnerDeactivateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    reason: str | None = None
    confirm: bool = True


class OwnerStatusUpdateRequest(BaseModel):
    status: str
    reason: str | None = None
