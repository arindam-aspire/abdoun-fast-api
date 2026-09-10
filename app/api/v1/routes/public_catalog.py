from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DBSessionDep
from app.models.live_schema import Area, City, Feature, PropertyCategory, PropertyType
from app.services.property_taxonomy import (
    is_dco_category,
    is_dco_property_type,
    sort_categories,
    sort_property_types,
)
from app.services.property_options import OPTION_GROUPS, list_property_options, normalize_group_key, serialize_option
from app.utils.api_response import raise_api_error, success_response
from app.utils.status_codes import STATUS_BAD_REQUEST

router = APIRouter()


@router.get(
    "/property-form-options",
    summary="List Add Property master-data options",
    description="Alias of /property-options. Returns DB-backed dropdown values from property_option_values.",
)
@router.get(
    "/property-options",
    summary="List Add Property master-data options",
    description="Returns DB-backed dropdown values from property_option_values. Filter with group=furnishing_status, floor, listing_purpose, completion_status, or direction.",
)
def get_property_options(
    db: DBSessionDep,
    group: str | None = None,
    is_active: bool | None = True,
) -> dict:
    normalized_group = normalize_group_key(group)
    if normalized_group and normalized_group not in OPTION_GROUPS:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="INVALID_VALUE",
            message="Unknown property option group",
            details=[{"field": "group", "code": "invalid_value", "message": "Unknown property option group"}],
        )
    options = list_property_options(db, group=normalized_group, is_active=is_active)
    grouped: dict[str, list[dict]] = {}
    for option in options:
        grouped.setdefault(option.group_key, []).append(serialize_option(option))
    return success_response(
        {"items": [serialize_option(option) for option in options], "groups": grouped, "total": len(options)}
    )


@router.get("/features")
def list_features(db: DBSessionDep, is_active: bool | None = None) -> dict:
    stmt = select(Feature).order_by(Feature.display_order.asc(), Feature.name.asc())
    if is_active is not None:
        stmt = stmt.where(Feature.is_active.is_(is_active))
    features = db.execute(stmt).scalars().all()
    category_ids = {feature.category_id for feature in features if feature.category_id}
    property_type_ids = {feature.property_type_id for feature in features if feature.property_type_id}
    categories = (
        db.execute(select(PropertyCategory).where(PropertyCategory.id.in_(category_ids))).scalars().all()
        if category_ids
        else []
    )
    property_types = (
        db.execute(select(PropertyType).where(PropertyType.id.in_(property_type_ids))).scalars().all()
        if property_type_ids
        else []
    )
    categories_by_id = {category.id: category for category in categories}
    property_types_by_id = {property_type.id: property_type for property_type in property_types}
    items = [
        {
            "id": feature.id,
            "name": feature.name,
            "slug": feature.slug,
            "category_id": feature.category_id,
            "property_type_id": feature.property_type_id,
            "feature_group": feature.feature_group,
            "display_order": feature.display_order,
            "is_active": bool(feature.is_active),
            "created_at": feature.created_at.isoformat() if feature.created_at else None,
            "updated_at": feature.updated_at.isoformat() if feature.updated_at else None,
            "category": (
                {
                    "id": categories_by_id[feature.category_id].id,
                    "name": categories_by_id[feature.category_id].name,
                    "slug": categories_by_id[feature.category_id].slug,
                }
                if feature.category_id and feature.category_id in categories_by_id
                else None
            ),
            "property_type": (
                {
                    "id": property_types_by_id[feature.property_type_id].id,
                    "category_id": property_types_by_id[feature.property_type_id].category_id,
                    "name": property_types_by_id[feature.property_type_id].name,
                    "slug": property_types_by_id[feature.property_type_id].slug,
                }
                if feature.property_type_id and feature.property_type_id in property_types_by_id
                else None
            ),
        }
        for feature in features
    ]
    return success_response({"items": items, "total": len(items)})


@router.get("/property-taxonomy")
def get_property_taxonomy(db: DBSessionDep) -> dict:
    categories = db.execute(
        select(PropertyCategory)
        .where(PropertyCategory.is_active.is_(True))
    ).scalars().all()
    types = db.execute(
        select(PropertyType)
        .where(PropertyType.is_active.is_(True))
    ).scalars().all()
    types_by_category: dict[int, list[PropertyType]] = {}
    for property_type in types:
        types_by_category.setdefault(property_type.category_id, []).append(property_type)

    data = [
        {
            "id": category.id,
            "name": category.name,
            "slug": category.slug,
            "property_types": [
                {
                    "id": property_type.id,
                    "category_id": property_type.category_id,
                    "name": property_type.name,
                    "slug": property_type.slug,
                }
                for property_type in sort_property_types(
                    category.slug,
                    [
                        property_type
                        for property_type in types_by_category.get(category.id, [])
                        if is_dco_property_type(category.slug, property_type)
                    ],
                )
            ],
        }
        for category in sort_categories([category for category in categories if is_dco_category(category)])
    ]
    return success_response({"data": data, "total": len(data)})


@router.get("/location-taxonomy")
def get_location_taxonomy(db: DBSessionDep) -> dict:
    cities = db.execute(
        select(City)
        .where(City.is_active.is_(True))
        .order_by(City.name.asc())
    ).scalars().all()
    areas = db.execute(
        select(Area)
        .where(Area.is_active.is_(True))
        .order_by(Area.name.asc())
    ).scalars().all()
    areas_by_city: dict[int, list[Area]] = {}
    for area in areas:
        areas_by_city.setdefault(area.city_id, []).append(area)

    data = [
        {
            "id": city.id,
            "name": city.name,
            "areas": [{"id": area.id, "name": area.name} for area in areas_by_city.get(city.id, [])],
        }
        for city in cities
    ]
    return success_response({"data": data, "total": len(data)})
