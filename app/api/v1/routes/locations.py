"""
API endpoints for cities and areas (locations)
"""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.property_normalized import City, Area

router = APIRouter()

DBSessionDep = Annotated[Session, Depends(get_db)]


@router.get("/cities")
def list_cities(
    db: DBSessionDep,
) -> dict:
    """
    Get list of all active cities.
    
    Returns a list of cities with their IDs and names.
    """
    stmt = select(City).where(City.is_active == True).order_by(City.name)
    cities = db.execute(stmt).scalars().all()
    
    return {
        "data": [
            {
                "id": city.id,
                "name": city.name,
            }
            for city in cities
        ],
        "total": len(cities)
    }


@router.get("/areas")
def list_areas(
    db: DBSessionDep,
    city: Optional[str] = Query(None, description="Filter areas by city name (case-insensitive)"),
) -> dict:
    """
    Get list of areas, optionally filtered by city.
    
    If city parameter is provided, returns only areas in that city.
    Otherwise, returns all active areas.
    """
    stmt = select(Area).join(City, Area.city_id == City.id)
    
    # Filter by city if provided
    if city:
        city_lower = city.lower()
        stmt = stmt.where(
            func.lower(City.name).contains(city_lower)
        )
    
    # Only active areas
    stmt = stmt.where(Area.is_active == True)
    stmt = stmt.order_by(City.name, Area.name)
    
    areas = db.execute(stmt).scalars().all()
    
    return {
        "data": [
            {
                "id": area.id,
                "name": area.name,
                "city_id": area.city_id,
                "city_name": area.city.name if area.city else None,
            }
            for area in areas
        ],
        "total": len(areas)
    }

