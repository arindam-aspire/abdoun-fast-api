"""Feature catalog filtering by property category and type.

Type-specific rows are those linked by property_type_id, or whose master-data
slug ends with ``-{property_type.slug}-feature``. Shared rows are category-level
amenities (no property type). A type filter returns both sets for that category.
"""

from __future__ import annotations

from typing import Any, NoReturn

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.live_schema import PropertyCategory, PropertyType
from app.utils.api_response import raise_api_error
from app.utils.status_codes import STATUS_BAD_REQUEST

SHARED_FEATURE_GROUPS = frozenset({"AMENITY", "AMENITIES"})


def is_shared_feature(feature: Any) -> bool:
    if getattr(feature, "property_type_id", None) is not None:
        return False
    group = str(getattr(feature, "feature_group", "") or "").upper()
    slug = str(getattr(feature, "slug", "") or "")
    if group in SHARED_FEATURE_GROUPS:
        return True
    return "-common-" in slug


def matches_property_type(feature: Any, property_type: Any) -> bool:
    type_id = getattr(property_type, "id", None)
    if getattr(feature, "property_type_id", None) is not None:
        return feature.property_type_id == type_id
    slug = str(getattr(feature, "slug", "") or "")
    type_slug = str(getattr(property_type, "slug", "") or "").strip()
    if not type_slug or not slug.endswith(f"-{type_slug}-feature"):
        return False
    feature_category_id = getattr(feature, "category_id", None)
    type_category_id = getattr(property_type, "category_id", None)
    if feature_category_id and type_category_id and feature_category_id != type_category_id:
        return False
    return True


def feature_applies_to_property_type(feature: Any, property_type: Any) -> bool:
    if matches_property_type(feature, property_type):
        return True
    if not is_shared_feature(feature):
        return False
    return getattr(feature, "category_id", None) == getattr(property_type, "category_id", None)


def _lookup_token(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    return str(value).strip().casefold()


def _invalid_filter(field: str, message: str) -> NoReturn:
    raise_api_error(
        status_code=STATUS_BAD_REQUEST,
        code="INVALID_VALUE",
        message=message,
        details=[{"field": field, "code": "invalid_value", "message": message}],
    )


def resolve_feature_scope(
    db: Session,
    *,
    category_id: int | None = None,
    category: str | None = None,
    property_type_id: int | None = None,
    property_type: str | None = None,
) -> tuple[Any | None, Any | None]:
    """Resolve optional category and property-type filters. Both may be absent."""
    category_token = _lookup_token(category)
    type_token = _lookup_token(property_type)
    if category_id is None and category_token is None and property_type_id is None and type_token is None:
        return None, None

    category_obj = None
    if category_id is not None:
        category_obj = db.get(PropertyCategory, category_id)
        if category_obj is None:
            _invalid_filter("category_id", "Unknown property category")
    elif category_token is not None:
        category_obj = db.execute(
            select(PropertyCategory).where(func.lower(PropertyCategory.slug) == category_token)
        ).scalars().first()
        if category_obj is None:
            category_obj = db.execute(
                select(PropertyCategory).where(func.lower(PropertyCategory.name) == category_token)
            ).scalars().first()
        if category_obj is None:
            _invalid_filter("category", "Unknown property category")

    type_obj = None
    if property_type_id is not None:
        type_obj = db.get(PropertyType, property_type_id)
        if type_obj is None:
            _invalid_filter("property_type_id", "Unknown property type")
    elif type_token is not None:
        stmt = select(PropertyType).where(func.lower(PropertyType.slug) == type_token)
        if category_obj is not None:
            stmt = stmt.where(PropertyType.category_id == category_obj.id)
        matches = list(db.execute(stmt).scalars().all())
        if not matches:
            name_stmt = select(PropertyType).where(func.lower(PropertyType.name) == type_token)
            if category_obj is not None:
                name_stmt = name_stmt.where(PropertyType.category_id == category_obj.id)
            matches = list(db.execute(name_stmt).scalars().all())
        if not matches:
            _invalid_filter("property_type", "Unknown property type")
        if len(matches) > 1:
            _invalid_filter(
                "property_type",
                "Property type matches more than one category; pass category or property_type_id",
            )
        type_obj = matches[0]

    if category_obj is not None and type_obj is not None and type_obj.category_id != category_obj.id:
        _invalid_filter("property_type_id", "Property type does not belong to the selected category")
    return category_obj, type_obj


def filter_features(
    features: list[Any],
    *,
    category: Any | None = None,
    property_type: Any | None = None,
) -> list[Any]:
    if property_type is not None:
        return [feature for feature in features if feature_applies_to_property_type(feature, property_type)]
    if category is not None:
        category_id = getattr(category, "id", None)
        return [feature for feature in features if getattr(feature, "category_id", None) == category_id]
    return list(features)
