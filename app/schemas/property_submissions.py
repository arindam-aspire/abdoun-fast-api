from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class PropertyLocationStepPayload(BaseModel):
    """Create Property → Location step. Extra keys from the wizard are preserved."""

    model_config = ConfigDict(extra="allow")

    show_location: bool = False


class PropertyDetailsStepPayload(BaseModel):
    """Create Property → Property Details step fields."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    furnishing_status: Any | None = Field(
        default=None,
        validation_alias=AliasChoices("furnishingStatus", "furnishing_status"),
        description="Master-data furnishing status id, slug, or name from GET /api/v1/property-options?group=furnishing_status.",
    )
    furnishing_status_id: Any | None = Field(
        default=None,
        validation_alias=AliasChoices("furnishingStatusId", "furnishing_status_id"),
        description="Selected furnishing status option id from the Master API.",
    )
    floor: Any | None = Field(
        default=None,
        description="Selected floor option id, slug, or name from GET /api/v1/property-options?group=floor.",
    )
    floor_id: Any | None = Field(
        default=None,
        validation_alias=AliasChoices("floorId", "floor_id"),
        description="Selected floor option id from the Master API.",
    )
    floor_number: Any | None = Field(
        default=None,
        validation_alias=AliasChoices("floorNumber", "floor_number"),
    )
    floor_level: Any | None = Field(
        default=None,
        validation_alias=AliasChoices("floorLevel", "floor_level"),
    )
    guard_name: str | None = Field(default=None, max_length=255)
    guard_phone_number: str | None = Field(
        default=None,
        description="Guard phone number in E.164 format, including country code.",
    )


def normalize_wizard_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept camelCase Add Property aliases without dropping extra wizard keys."""
    if not isinstance(payload, dict):
        return payload
    normalized = dict(payload)
    details = normalized.get("property_details")
    if details is None and isinstance(normalized.get("propertyDetails"), dict):
        details = normalized["propertyDetails"]
        normalized["property_details"] = details
    if isinstance(details, dict):
        normalized["property_details"] = PropertyDetailsStepPayload.model_validate(details).model_dump(
            exclude_unset=True
        )
    return normalized


class PropertySubmissionCreateRequest(BaseModel):
    route_through_agency: bool = False
    agency_id: UUID | None = None
    payload: dict[str, Any] = Field(
        ...,
        description=(
            "Eight-step wizard payload. Dropdown values come from GET /api/v1/property-options and "
            "features from GET /api/v1/features. Location accepts latitude/longitude (or map_pin) and "
            "show_location. Property area is the single numeric property_details.built_up_area value. "
            "Property details accept apartment_number, plot_number, basin_number, year_built, direction, "
            "floor/floor_id, floor_number, completion_status, and furnishingStatus/furnishing_status aliases. "
            "basic_information.listing_purpose accepts sale, rent, or sale_or_rent. "
            "Property details accept built_up_area (> 0) with built_up_area_unit ('sqm' or 'sqft'). "
            "Property details also accept optional guard_name and guard_phone_number. "
            "Pricing accepts the legacy price plus furnishing-specific sale/rent price fields, "
            "service_charge, and maintenance_fee with currency codes "
            "(JOD, USD, GBP, INR; default JOD). Drafts preserve entered amounts/currencies; "
            "submit converts all pricing amounts to JOD using live exchange rates. "
            "Owner entries may select an existing owner with owner_user_id. "
            "DLD number is not accepted or persisted by this workflow. "
            "payload.property_details.reference_number is server-generated and ignored if provided."
        ),
    )
    current_step: int = 1
    last_completed_step: int = 0

    @field_validator("payload")
    @classmethod
    def normalize_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        return normalize_wizard_payload(value)


class PropertySubmissionUpdateRequest(BaseModel):
    action: Literal["save_draft"] = "save_draft"
    route_through_agency: bool | None = None
    agency_id: UUID | None = None
    current_step: int
    last_completed_step: int
    payload: dict[str, Any] = Field(
        ...,
        description=(
            "Eight-step wizard payload using DB-backed /property-options and /features values. "
            "Location accepts latitude/longitude (or map_pin) and show_location. "
            "Property area is a single property_details.built_up_area value. "
            "Owner entries may select an existing owner with owner_user_id. DLD number is retired. "
            "Property details accept built_up_area (> 0) with built_up_area_unit ('sqm' or 'sqft'). "
            "Property details also accept optional guard_name and guard_phone_number. "
            "Property details persist furnishingStatus/furnishing_status and floor/floor_id from "
            "GET /api/v1/property-options. "
            "Pricing accepts price, service_charge, and maintenance_fee with currency codes "
            "(JOD, USD, GBP, INR; default JOD). Drafts preserve entered amounts/currencies; "
            "submit converts all pricing amounts to JOD using live exchange rates. "
            "payload.property_details.reference_number is server-generated and ignored if provided."
        ),
    )

    @field_validator("payload")
    @classmethod
    def normalize_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        return normalize_wizard_payload(value)


class PropertySubmissionDirectSubmitRequest(BaseModel):
    route_through_agency: bool = False
    agency_id: UUID | None = None
    payload: dict[str, Any] = Field(
        ...,
        description=(
            "Eight-step wizard payload using DB-backed /property-options and /features values. "
            "Location accepts latitude/longitude (or map_pin) and show_location. "
            "Property area is a single property_details.built_up_area value. "
            "Owner entries may select an existing owner with owner_user_id. DLD number is retired. "
            "Property details accept built_up_area (> 0) with built_up_area_unit ('sqm' or 'sqft'). "
            "Property details also accept optional guard_name and guard_phone_number. "
            "Property details persist furnishingStatus/furnishing_status and floor/floor_id from "
            "GET /api/v1/property-options. "
            "Pricing accepts price, service_charge, and maintenance_fee with currency codes "
            "(JOD, USD, GBP, INR; default JOD). Drafts preserve entered amounts/currencies; "
            "submit converts all pricing amounts to JOD using live exchange rates. "
            "payload.property_details.reference_number is server-generated and ignored if provided."
        ),
    )
    confirm_submit: bool

    @field_validator("payload")
    @classmethod
    def normalize_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        return normalize_wizard_payload(value)


class PropertySubmissionSubmitRequest(BaseModel):
    confirm_submit: bool
    review_comment: str | None = None


class PropertySubmissionReviewRequest(BaseModel):
    action: Literal["approve", "reject"]
    reason: str | None = None


class PropertyAssignAgentRequest(BaseModel):
    agent_id: str | None = None
