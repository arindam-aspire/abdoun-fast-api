from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class PropertyLocationStepPayload(BaseModel):
    """Create Property → Location step. Extra keys from the wizard are preserved."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    show_location: bool = False
    gov_code: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "gov_code",
            "govCode",
            "GOV_CODE",
            "government_code",
            "governmentCode",
            "governate_code",
            "governorate_code",
        ),
        description="Governate code from GET /dls-locations?level=gov.",
    )
    gov_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "gov_name",
            "govName",
            "GOV_NAME",
            "government_name",
            "governmentName",
            "governorate",
            "governate",
        ),
    )
    dept_code: str | None = Field(
        default=None,
        validation_alias=AliasChoices("dept_code", "deptCode", "DEPT_CODE"),
    )
    dept_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("dept_name", "deptName", "DEPT_NAME", "directorate"),
    )
    vill_code: str | None = Field(
        default=None,
        validation_alias=AliasChoices("vill_code", "villCode", "VILL_CODE", "village_code"),
    )
    vill_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("vill_name", "villName", "VILL_NAME", "village"),
    )
    hod_code: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "hod_code",
            "hodCode",
            "HOD_CODE",
            "parcel_name_code",
            "parcelNameCode",
        ),
        description="Parcel Name (HOD) code from GET /dls-locations?level=hod.",
    )
    hod_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "hod_name",
            "hodName",
            "HOD_NAME",
            "parcel_name",
            "parcelName",
        ),
        description="Parcel Name (HOD) label from GET /dls-locations?level=hod.",
    )
    sect_code: str | None = Field(
        default=None,
        validation_alias=AliasChoices("sect_code", "sectCode", "SECT_CODE", "section_code"),
    )
    sect_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("sect_name", "sectName", "SECT_NAME", "section"),
    )
    apartment_number: str | None = Field(
        default=None,
        validation_alias=AliasChoices("apartmentNumber", "apartment_number", "apartment"),
        description="Apartment for Residential/Commercial only; ignored for Land.",
    )
    plot_number: str | None = Field(
        default=None,
        validation_alias=AliasChoices("plotNumber", "plot_number"),
    )
    parcel_number: str | None = Field(
        default=None,
        validation_alias=AliasChoices("parcelNumber", "parcel_number"),
        description="Parcel Number for Residential/Commercial only; ignored for Land.",
    )
    building_number: str | None = Field(
        default=None,
        validation_alias=AliasChoices("buildingNumber", "building_number", "building"),
        description="Building Number for Residential/Commercial.",
    )
    floor_number: Any | None = Field(
        default=None,
        validation_alias=AliasChoices("floorNumber", "floor_number"),
        description="Floor as a numeric string when present (Residential/Commercial).",
    )
    floor: Any | None = Field(
        default=None,
        description="Floor option id, slug, or name from GET /api/v1/property-options?group=floor.",
    )
    floor_id: Any | None = Field(
        default=None,
        validation_alias=AliasChoices("floorId", "floor_id"),
        description="Selected floor option id from the Master API (Residential/Commercial).",
    )
    land_type: Any | None = Field(
        default=None,
        validation_alias=AliasChoices("landType", "land_type"),
        description=(
            "Land Type from GET /api/v1/property-options?group=land_type. "
            "Residential/Commercial only; ignored for Land."
        ),
    )
    land_type_id: Any | None = Field(
        default=None,
        validation_alias=AliasChoices("landTypeId", "land_type_id"),
        description="Land Type option id from GET /api/v1/property-options?group=land_type.",
    )


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
    land_type: Any | None = Field(
        default=None,
        validation_alias=AliasChoices("landType", "land_type"),
        description=(
            "Master-data Land Type id, slug, or name from GET /api/v1/property-options?group=land_type. "
            "Applies to Residential and Commercial only; ignored for Land."
        ),
    )
    land_type_id: Any | None = Field(
        default=None,
        validation_alias=AliasChoices("landTypeId", "land_type_id"),
        description="Selected Land Type option id from the Master API (Residential/Commercial only).",
    )
    apartment_number: str | None = Field(
        default=None,
        validation_alias=AliasChoices("apartmentNumber", "apartment_number", "apartment"),
        description="Apartment for Residential/Commercial only; ignored for Land.",
    )
    plot_number: str | None = Field(
        default=None,
        validation_alias=AliasChoices("plotNumber", "plot_number"),
    )
    parcel_number: str | None = Field(
        default=None,
        validation_alias=AliasChoices("parcelNumber", "parcel_number"),
        description="Parcel Number for Residential/Commercial only; ignored for Land.",
    )
    building_number: str | None = Field(
        default=None,
        validation_alias=AliasChoices("buildingNumber", "building_number", "building"),
        description="Building Number for Residential/Commercial.",
    )
    parking_spaces: Any | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "parkingSpaces",
            "parking_spaces",
            "parking_space",
            "parkingSpace",
            "parking",
        ),
        description="Manual parking-space count. Accepts a non-negative integer, not a dropdown option id.",
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
    location = normalized.get("location")
    if isinstance(location, dict):
        normalized["location"] = PropertyLocationStepPayload.model_validate(location).model_dump(
            exclude_unset=True
        )
    details = normalized.get("property_details")
    if details is None and isinstance(normalized.get("propertyDetails"), dict):
        details = normalized["propertyDetails"]
        normalized["property_details"] = details
    if isinstance(details, dict):
        normalized["property_details"] = PropertyDetailsStepPayload.model_validate(details).model_dump(
            exclude_unset=True
        )
    return normalized


VERIFY_THROUGH_AGENCY_DESCRIPTION = (
    "Owner-only. When false, agency_id may be null and the property is submitted directly to Super Admin "
    "for approval, rejection, or edit request. When true, a valid agency_id is required and the existing "
    "agency verification workflow is used. Agency/Admin/other roles ignore this flag."
)


class PropertySubmissionCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    route_through_agency: bool = Field(
        default=False,
        validation_alias=AliasChoices("verify_through_agency", "route_through_agency"),
        description=VERIFY_THROUGH_AGENCY_DESCRIPTION,
    )
    agency_id: UUID | None = None
    payload: dict[str, Any] = Field(
        ...,
        description=(
            "Eight-step wizard payload. Dropdown values come from GET /api/v1/property-options and "
            "features from GET /api/v1/features. Location accepts latitude/longitude (or map_pin) and "
            "show_location. Property area is the single numeric property_details.built_up_area value. "
            "Property details accept category-dependent optional identifiers: "
            "Residential/Commercial — land_type_id, floor_number, apartment_number, plot_number, "
            "parcel_number, building_number. Land accepts plot_number only and ignores land_type_id, "
            "parcel_number, building_number, apartment_number, and floor_number. Basin Number is not accepted. "
            "DLS hierarchy uses gov_code/gov_name, dept_*, vill_*, hod_*, sect_* "
            "(government_* aliases accepted). "
            "Also accept year_built, direction, floor/floor_id, completion_status, "
            "parking_spaces as a manual non-negative integer, "
            "and furnishingStatus/furnishing_status aliases. "
            "basic_information.listing_purpose accepts sale, rent, or sale_or_rent. "
            "Building area is stored and returned in sqm only. "
            "Property details also accept optional guard_name and guard_phone_number. "
            "Pricing accepts the legacy price plus furnishing-specific sale/rent price fields, "
            "service_charge, and maintenance_fee with currency codes "
            "(JOD, USD, GBP, INR; default JOD). Drafts preserve entered amounts/currencies; "
            "submit converts all pricing amounts to JOD using live exchange rates. "
            "Owner entries may select an existing owner with owner_user_id and may send Owner ID or Passport. "
            "DLD number is not accepted or persisted by this workflow. "
            "payload.property_details.reference_number is a server-generated category/type prefix plus a global sequence and is ignored if provided."
        ),
    )
    current_step: int = 1
    last_completed_step: int = 0

    @field_validator("payload")
    @classmethod
    def normalize_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        return normalize_wizard_payload(value)


class PropertySubmissionUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    action: Literal["save_draft"] = "save_draft"
    route_through_agency: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("verify_through_agency", "route_through_agency"),
        description=VERIFY_THROUGH_AGENCY_DESCRIPTION,
    )
    agency_id: UUID | None = None
    current_step: int
    last_completed_step: int
    payload: dict[str, Any] = Field(
        ...,
        description=(
            "Eight-step wizard payload using DB-backed /property-options and /features values. "
            "Location accepts latitude/longitude (or map_pin) and show_location. "
            "Property area is a single property_details.built_up_area value. "
            "Owner entries may select an existing owner with owner_user_id and may send Owner ID or Passport. DLD number is retired. "
            "Building area is stored and returned in sqm only. "
            "Property details also accept optional guard_name and guard_phone_number. "
            "Property details persist furnishingStatus/furnishing_status, floor/floor_id, and "
            "landType/land_type_id from GET /api/v1/property-options. "
            "Land Type applies to Residential/Commercial only. "
            "Parking space is a manual property_details.parking_spaces integer. "
            "Pricing accepts price, service_charge, and maintenance_fee with currency codes "
            "(JOD, USD, GBP, INR; default JOD). Drafts preserve entered amounts/currencies; "
            "submit converts all pricing amounts to JOD using live exchange rates. "
            "payload.property_details.reference_number is a server-generated category/type prefix plus a global sequence and is ignored if provided."
        ),
    )

    @field_validator("payload")
    @classmethod
    def normalize_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        return normalize_wizard_payload(value)


class PropertySubmissionDirectSubmitRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    route_through_agency: bool = Field(
        default=False,
        validation_alias=AliasChoices("verify_through_agency", "route_through_agency"),
        description=VERIFY_THROUGH_AGENCY_DESCRIPTION,
    )
    agency_id: UUID | None = None
    payload: dict[str, Any] = Field(
        ...,
        description=(
            "Eight-step wizard payload using DB-backed /property-options and /features values. "
            "Location accepts latitude/longitude (or map_pin) and show_location. "
            "Property area is a single property_details.built_up_area value. "
            "Owner entries may select an existing owner with owner_user_id and may send Owner ID or Passport. DLD number is retired. "
            "Building area is stored and returned in sqm only. "
            "Property details also accept optional guard_name and guard_phone_number. "
            "Property details persist furnishingStatus/furnishing_status, floor/floor_id, and "
            "landType/land_type_id from GET /api/v1/property-options. "
            "Land Type applies to Residential/Commercial only. "
            "Parking space is a manual property_details.parking_spaces integer. "
            "Pricing accepts price, service_charge, and maintenance_fee with currency codes "
            "(JOD, USD, GBP, INR; default JOD). Drafts preserve entered amounts/currencies; "
            "submit converts all pricing amounts to JOD using live exchange rates. "
            "payload.property_details.reference_number is a server-generated category/type prefix plus a global sequence and is ignored if provided."
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
