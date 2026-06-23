from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DBSessionDep
from app.models.live_schema import Area, City, Feature, PropertyCategory, PropertyType
from app.services.public_properties import serialize_feature_catalog_item
from app.utils.api_response import success_response

router = APIRouter()


@router.get("/features")
def list_features(db: DBSessionDep, is_active: bool | None = None) -> dict:
    stmt = select(Feature).order_by(Feature.display_order.asc(), Feature.name.asc())
    if is_active is not None:
        stmt = stmt.where(Feature.is_active.is_(is_active))
    items = [serialize_feature_catalog_item(db, feature) for feature in db.execute(stmt).scalars().all()]
    return success_response({"items": items, "total": len(items)})


@router.get("/property-taxonomy")
def get_property_taxonomy(db: DBSessionDep) -> dict:
    categories = db.execute(
        select(PropertyCategory)
        .where(PropertyCategory.is_active.is_(True))
        .order_by(PropertyCategory.name.asc())
    ).scalars().all()
    types = db.execute(
        select(PropertyType)
        .where(PropertyType.is_active.is_(True))
        .order_by(PropertyType.name.asc())
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
                for property_type in types_by_category.get(category.id, [])
            ],
        }
        for category in categories
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

