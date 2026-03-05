from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload
import json

from app.models.property_normalized import PropertyNormalized as Property
from app.schemas.property import PropertySearchRequest, PropertySearchResult


def search_properties_service(db: Session, request: PropertySearchRequest) -> list[PropertySearchResult]:
    """
    Execute the property search based on the provided request filters.
    
    This service handles the spatial queries and model joining logic.
    """
    stmt = select(Property).options(
        joinedload(Property.category),
        joinedload(Property.type),
        joinedload(Property.city),
        joinedload(Property.area_rel),
    )

    if request.mode == "bounds":
        if not request.bounds:
            return []
        b = request.bounds
        envelope = func.ST_MakeEnvelope(
            b.min_lng,
            b.min_lat,
            b.max_lng,
            b.max_lat,
            4326,
        )
        stmt = stmt.where(
            func.ST_Intersects(Property.location, envelope)
        )
    elif request.mode == "polygon":
        if not request.polygon:
            return []
        geojson_str = json.dumps(request.polygon.geojson)
        geom = func.ST_GeomFromGeoJSON(geojson_str)
        stmt = stmt.where(func.ST_Within(Property.location, geom))

    stmt = stmt.limit(request.limit)

    results = db.execute(stmt).unique().scalars().all()
    return [PropertySearchResult.from_orm_obj(p) for p in results]
