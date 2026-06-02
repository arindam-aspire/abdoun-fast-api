"""Pydantic schemas for feature / amenity taxonomy APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.utils.constants import FeatureGroup


FeatureGroupLiteral = Literal["FEATURE", "AMENITY"]


class FeatureCategoryRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str


class FeaturePropertyTypeRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    name: str
    slug: str


class FeatureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    category_id: Optional[int] = None
    property_type_id: Optional[int] = None
    feature_group: str
    display_order: int
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    category: Optional[FeatureCategoryRef] = None
    property_type: Optional[FeaturePropertyTypeRef] = None


class FeatureCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    slug: Optional[str] = Field(default=None, max_length=100)
    category_id: int
    property_type_id: Optional[int] = None
    feature_group: FeatureGroupLiteral = FeatureGroup.FEATURE
    display_order: int = 0
    is_active: bool = True

    @field_validator("feature_group", mode="before")
    @classmethod
    def normalize_feature_group(cls, value: object) -> str:
        if value is None:
            return FeatureGroup.FEATURE
        normalized = str(value).strip().upper()
        if normalized not in FeatureGroup.ALLOWED:
            raise ValueError(FeatureGroup.FEATURE)
        return normalized


class FeatureUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    slug: Optional[str] = Field(default=None, max_length=100)
    category_id: Optional[int] = None
    property_type_id: Optional[int] = None
    feature_group: Optional[FeatureGroupLiteral] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator("feature_group", mode="before")
    @classmethod
    def normalize_feature_group(cls, value: object) -> object:
        if value is None:
            return None
        normalized = str(value).strip().upper()
        if normalized not in FeatureGroup.ALLOWED:
            raise ValueError(FeatureGroup.FEATURE)
        return normalized


class FeatureListFilters(BaseModel):
    """Query filters for listing features."""

    category_id: Optional[int] = None
    property_type_id: Optional[int] = None
    feature_group: Optional[FeatureGroupLiteral] = Field(
        default=None,
        validation_alias=AliasChoices("feature_group", "featureGroup"),
    )
    is_active: Optional[bool] = True
    include_legacy: bool = Field(
        default=True,
        description=(
            "When filtering by category/type, also include rows linked via "
            "legacy category_features / type_features tables."
        ),
    )

    @field_validator("feature_group", mode="before")
    @classmethod
    def normalize_feature_group(cls, value: object) -> object:
        if value is None:
            return None
        return str(value).strip().upper()


class FeatureListResponse(BaseModel):
    items: list[FeatureResponse]
    total: int
