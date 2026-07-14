from __future__ import annotations

import re
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


PHONE_E164_REGEX = re.compile(r"^\+[1-9]\d{7,14}$")
ALLOWED_IDENTITY_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
IDENTITY_DOCUMENT_MAX_BYTES = 5 * 1024 * 1024


def normalize_phone(value: str) -> str:
    cleaned = re.sub(r"[\s\-()]", "", (value or "").strip())
    if cleaned and not cleaned.startswith("+") and cleaned.isdigit():
        cleaned = f"+{cleaned}"
    return cleaned


def validate_e164_phone(value: str, *, field_name: str = "phone") -> str:
    normalized = normalize_phone(value)
    if not PHONE_E164_REGEX.match(normalized):
        raise ValueError(f"{field_name} must include country code in E.164 format (e.g. +9627xxxxxxx)")
    return normalized


class AgentInviteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    email: str | None = None
    phone_number: str | None = Field(
        default=None,
        validation_alias=AliasChoices("phoneNumber", "phone_number", "phone"),
    )
    full_name: str | None = Field(default=None, validation_alias=AliasChoices("fullName", "full_name"))
    service_area: str | None = Field(default=None, validation_alias=AliasChoices("serviceArea", "service_area"))

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
        if value is None or not str(value).strip():
            return None
        return validate_e164_phone(value, field_name="phone_number")

    @model_validator(mode="after")
    def require_email_or_phone(self) -> "AgentInviteRequest":
        if not self.email and not self.phone_number:
            raise ValueError("Either email or phone_number is required")
        return self


class AgentReviewRequest(BaseModel):
    status: str
    reason: str | None = None


class AgentStatusUpdateRequest(BaseModel):
    status: str
    reason: str | None = None


class AgentInvitationAcceptRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


class AgentPasswordSetupRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


class AgentOnboardingFormRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    token: str | None = None
    full_name: str = Field(min_length=2, validation_alias=AliasChoices("fullName", "full_name"))
    # Accepted for backward compatibility only — backend ignores this and uses the invitation email.
    email: EmailStr | None = None
    phone: str = Field(validation_alias=AliasChoices("phone", "phoneNumber", "phone_number"))
    whatsapp_number: str | None = Field(
        default=None,
        validation_alias=AliasChoices("whatsappNumber", "whatsapp_number", "whatsapp"),
    )
    service_area_ids: list[int] = Field(
        min_length=1,
        validation_alias=AliasChoices("serviceAreaIds", "service_area_ids", "serviceAreas", "service_areas"),
    )
    position: str = Field(min_length=1)
    identity_document_url: str = Field(
        min_length=1,
        validation_alias=AliasChoices(
            "identityDocumentUrl",
            "identity_document_url",
            "identityDocument",
            "identity_document",
        ),
    )

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("full_name must be at least 2 characters")
        return cleaned

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        return validate_e164_phone(value, field_name="phone")

    @field_validator("whatsapp_number")
    @classmethod
    def validate_whatsapp(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return None
        return validate_e164_phone(value, field_name="whatsapp_number")

    @field_validator("service_area_ids", mode="before")
    @classmethod
    def coerce_service_area_ids(cls, value: Any) -> list[int]:
        if value is None:
            return []
        if isinstance(value, int):
            return [value]
        if isinstance(value, list):
            ids: list[int] = []
            for item in value:
                if isinstance(item, dict) and "id" in item:
                    ids.append(int(item["id"]))
                else:
                    ids.append(int(item))
            return ids
        raise ValueError("service_area_ids must be a non-empty list of area ids")

    @field_validator("service_area_ids")
    @classmethod
    def require_service_area_ids(cls, value: list[int]) -> list[int]:
        unique = sorted(set(value))
        if not unique:
            raise ValueError("At least one service area is required")
        if any(item <= 0 for item in unique):
            raise ValueError("service_area_ids must be positive integers")
        return unique

    @field_validator("position")
    @classmethod
    def validate_position(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("position is required")
        return cleaned

    @field_validator("identity_document_url")
    @classmethod
    def validate_identity_document(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("identity document is required")
        return cleaned


class AgentDocumentUploadRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    token: str
    file_name: str = Field(min_length=1, validation_alias=AliasChoices("fileName", "file_name"))
    content_type: str = Field(min_length=1, validation_alias=AliasChoices("contentType", "content_type"))
    file_size: int = Field(
        ge=1,
        le=IDENTITY_DOCUMENT_MAX_BYTES,
        validation_alias=AliasChoices("fileSize", "file_size"),
    )

    @field_validator("file_name")
    @classmethod
    def validate_extension(cls, value: str) -> str:
        lowered = value.strip().lower()
        if not any(lowered.endswith(ext) for ext in ALLOWED_IDENTITY_EXTENSIONS):
            raise ValueError("identity document must be PDF, JPG, or PNG")
        return value.strip()


class ManualOnboardAgentRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    full_name: str = Field(min_length=2, validation_alias=AliasChoices("fullName", "full_name"))
    email: EmailStr
    phone: str = Field(validation_alias=AliasChoices("phone", "phoneNumber", "phone_number"))
    whatsapp_number: str | None = Field(
        default=None,
        validation_alias=AliasChoices("whatsappNumber", "whatsapp_number", "whatsapp"),
    )
    service_area_ids: list[int] = Field(
        min_length=1,
        validation_alias=AliasChoices("serviceAreaIds", "service_area_ids", "serviceAreas", "service_areas"),
    )
    position: str = Field(min_length=1)
    identity_document_url: str = Field(
        min_length=1,
        validation_alias=AliasChoices(
            "identityDocumentUrl",
            "identity_document_url",
            "identityDocument",
            "identity_document",
        ),
    )

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("full_name must be at least 2 characters")
        return cleaned

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        return validate_e164_phone(value, field_name="phone")

    @field_validator("whatsapp_number")
    @classmethod
    def validate_whatsapp(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return None
        return validate_e164_phone(value, field_name="whatsapp_number")

    @field_validator("service_area_ids", mode="before")
    @classmethod
    def coerce_service_area_ids(cls, value: Any) -> list[int]:
        if value is None:
            return []
        if isinstance(value, int):
            return [value]
        if isinstance(value, list):
            ids: list[int] = []
            for item in value:
                if isinstance(item, dict) and "id" in item:
                    ids.append(int(item["id"]))
                else:
                    ids.append(int(item))
            return ids
        raise ValueError("service_area_ids must be a non-empty list of area ids")

    @field_validator("service_area_ids")
    @classmethod
    def require_service_area_ids(cls, value: list[int]) -> list[int]:
        unique = sorted(set(value))
        if not unique:
            raise ValueError("At least one service area is required")
        if any(item <= 0 for item in unique):
            raise ValueError("service_area_ids must be positive integers")
        return unique

    @field_validator("position")
    @classmethod
    def validate_position(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("identity_document_url")
    @classmethod
    def validate_identity_document(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None
