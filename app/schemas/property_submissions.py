from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PropertyLocationStepPayload(BaseModel):
    """Create Property → Location step. Extra keys from the wizard are preserved."""

    model_config = ConfigDict(extra="allow")

    show_location: bool = False


class PropertyDetailsStepPayload(BaseModel):
    """Create Property → Property Details step fields."""

    model_config = ConfigDict(extra="allow")

    guard_name: str | None = Field(default=None, max_length=255)
    guard_phone_number: str | None = Field(
        default=None,
        description="Guard phone number in E.164 format, including country code.",
    )


class PropertySubmissionCreateRequest(BaseModel):
    route_through_agency: bool = False
    agency_id: UUID | None = None
    payload: dict[str, Any] = Field(
        ...,
        description=(
            "Wizard payload. Location step accepts payload.location.show_location (bool, default false). "
            "Property details accept built_up_area (> 0) with built_up_area_unit ('sqm' or 'sqft'). "
            "Property details also accept optional guard_name and guard_phone_number. "
            "Pricing accepts price, service_charge, and maintenance_fee with currency codes "
            "(JOD, USD, GBP, INR; default JOD). Drafts preserve entered amounts/currencies; "
            "submit converts all pricing amounts to JOD using live exchange rates. "
            "payload.property_details.reference_number is server-generated and ignored if provided."
        ),
    )
    current_step: int = 1
    last_completed_step: int = 0


class PropertySubmissionUpdateRequest(BaseModel):
    action: Literal["save_draft"] = "save_draft"
    route_through_agency: bool | None = None
    agency_id: UUID | None = None
    current_step: int
    last_completed_step: int
    payload: dict[str, Any] = Field(
        ...,
        description=(
            "Wizard payload. Location step accepts payload.location.show_location (bool, default false). "
            "Property details accept built_up_area (> 0) with built_up_area_unit ('sqm' or 'sqft'). "
            "Property details also accept optional guard_name and guard_phone_number. "
            "Pricing accepts price, service_charge, and maintenance_fee with currency codes "
            "(JOD, USD, GBP, INR; default JOD). Drafts preserve entered amounts/currencies; "
            "submit converts all pricing amounts to JOD using live exchange rates. "
            "payload.property_details.reference_number is server-generated and ignored if provided."
        ),
    )


class PropertySubmissionDirectSubmitRequest(BaseModel):
    route_through_agency: bool = False
    agency_id: UUID | None = None
    payload: dict[str, Any] = Field(
        ...,
        description=(
            "Wizard payload. Location step accepts payload.location.show_location (bool, default false). "
            "Property details accept built_up_area (> 0) with built_up_area_unit ('sqm' or 'sqft'). "
            "Property details also accept optional guard_name and guard_phone_number. "
            "Pricing accepts price, service_charge, and maintenance_fee with currency codes "
            "(JOD, USD, GBP, INR; default JOD). Drafts preserve entered amounts/currencies; "
            "submit converts all pricing amounts to JOD using live exchange rates. "
            "payload.property_details.reference_number is server-generated and ignored if provided."
        ),
    )
    confirm_submit: bool


class PropertySubmissionSubmitRequest(BaseModel):
    confirm_submit: bool
    review_comment: str | None = None


class PropertySubmissionReviewRequest(BaseModel):
    action: Literal["approve", "reject"]
    reason: str | None = None


class PropertyAssignAgentRequest(BaseModel):
    agent_id: str | None = None
