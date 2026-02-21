"""
Property schemas for API request/response models.

This module defines Pydantic models for property-related API operations,
including search results, property details, search requests, and responses.
"""

from __future__ import annotations

from typing import Any, Literal, Optional
import json

from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.property import Property
from app.utils.constants import Defaults


class PropertySearchResult(BaseModel):
    """
    Schema for property search results.
    
    Used in property listings and search results to provide essential
    property information for display in search results.
    
    Attributes:
        id: Unique property identifier
        title: Property title/name
        price: Property price (selling or rent price)
        price_currency: Currency code for the price (e.g., 'JOD', 'USD')
        bedrooms: Number of bedrooms
        bathrooms: Number of bathrooms
        thumbnail: URL to the first/thumbnail image
        lat: Latitude coordinate
        lng: Longitude coordinate
    """
    id: int
    title: str
    price: Optional[float] = None
    price_currency: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    thumbnail: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None

    @classmethod
    def from_orm_obj(cls, obj: Property) -> "PropertySearchResult":
        """
        Create PropertySearchResult from a Property ORM object.
        
        Args:
            obj: Property database model instance
            
        Returns:
            PropertySearchResult instance with data from the ORM object
        """
        price = obj.selling_price_amount or obj.rent_price_amount
        currency = obj.selling_price_currency or obj.rent_price_currency
        thumbnail = (obj.images or [None])[0]
        # Handle "nan" titles
        title = obj.title if obj.title and str(obj.title).lower() not in ("nan", "none") else Defaults.UNTITLED_PROPERTY
        return cls(
            id=obj.id,
            title=title,
            price=float(price) if price is not None else None,
            price_currency=currency,
            bedrooms=obj.bedrooms,
            bathrooms=obj.bathrooms,
            thumbnail=thumbnail,
            lat=obj.latitude,
            lng=obj.longitude,
        )


class PropertyDetail(BaseModel):
    """
    Schema for detailed property information.
    
    Used for property detail endpoints to provide comprehensive
    property information including all available fields.
    
    Attributes:
        id: Unique property identifier
        url: Original property URL from source
        title: Property title/name
        description: Property description
        category: Property category (e.g., 'Apartment', 'Villa')
        status: Property status (e.g., 'For Sale', 'For Rent')
        selling_price_amount: Selling price amount
        selling_price_currency: Currency for selling price
        rent_price_amount: Rent price amount
        rent_price_currency: Currency for rent price
        bedrooms: Number of bedrooms
        bathrooms: Number of bathrooms
        built_up_area: Built-up area in square meters
        features: List of property features
        more_features: Additional property features
        images: List of image URLs
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        location_name: Name of the location/area
    """
    id: int
    url: Optional[str] = None
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    selling_price_amount: Optional[float] = None
    selling_price_currency: Optional[str] = None
    rent_price_amount: Optional[float] = None
    rent_price_currency: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    built_up_area: Optional[float] = None
    features: Optional[list[Any]] = None
    more_features: Optional[list[Any]] = None
    images: Optional[list[str]] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None

    @classmethod
    def from_orm_obj(cls, obj: Property) -> "PropertyDetail":
        """
        Create PropertyDetail from a Property ORM object.
        
        Args:
            obj: Property database model instance
            
        Returns:
            PropertyDetail instance with data from the ORM object
        """
        # Handle "nan" titles
        title = obj.title if obj.title and str(obj.title).lower() not in ("nan", "none") else Defaults.UNTITLED_PROPERTY
        return cls(
            id=obj.id,
            url=obj.url,
            title=title,
            description=obj.description,
            category=obj.category,
            status=obj.status,
            selling_price_amount=float(obj.selling_price_amount)
            if obj.selling_price_amount is not None
            else None,
            selling_price_currency=obj.selling_price_currency,
            rent_price_amount=float(obj.rent_price_amount)
            if obj.rent_price_amount is not None
            else None,
            rent_price_currency=obj.rent_price_currency,
            bedrooms=obj.bedrooms,
            bathrooms=obj.bathrooms,
            built_up_area=float(obj.built_up_area)
            if obj.built_up_area is not None
            else None,
            features=obj.features,
            more_features=obj.more_features,
            images=obj.images,
            latitude=obj.latitude,
            longitude=obj.longitude,
            location_name=obj.location_name,
        )


class BoundsFilter(BaseModel):
    """
    Schema for bounding box filter in property search.
    
    Defines a rectangular geographic area using minimum and maximum
    latitude and longitude coordinates.
    
    Attributes:
        min_lng: Minimum longitude (western boundary)
        min_lat: Minimum latitude (southern boundary)
        max_lng: Maximum longitude (eastern boundary)
        max_lat: Maximum latitude (northern boundary)
    """
    min_lng: float
    min_lat: float
    max_lng: float
    max_lat: float


class PolygonFilter(BaseModel):
    """
    Schema for polygon filter in property search.
    
    Defines a custom polygon area using GeoJSON format for
    more complex geographic searches.
    
    Attributes:
        geojson: GeoJSON Polygon object containing the polygon coordinates
    """
    geojson: dict = Field(
        ...,
        description="GeoJSON Polygon object",
    )


SearchMode = Literal["bounds", "polygon"]
"""Search mode type: either 'bounds' for rectangular area or 'polygon' for custom shape."""


class PropertySearchRequest(BaseModel):
    """
    Schema for property search request.
    
    Supports two search modes:
    - bounds: Search within a rectangular bounding box
    - polygon: Search within a custom polygon shape (GeoJSON)
    
    Attributes:
        mode: Search mode ('bounds' or 'polygon')
        bounds: Bounding box filter (required when mode is 'bounds')
        polygon: Polygon filter (required when mode is 'polygon')
        limit: Maximum number of results to return
    """
    mode: SearchMode
    bounds: Optional[BoundsFilter] = None
    polygon: Optional[PolygonFilter] = None
    limit: int = Defaults.MAX_SEARCH_LIMIT

    def execute(self, db: Session) -> list[PropertySearchResult]:
        """
        Execute the search query against the database.
        
        Performs a spatial query based on the search mode and filters,
        returning properties that intersect with the specified area.
        
        Args:
            db: SQLAlchemy database session
            
        Returns:
            List of PropertySearchResult objects matching the search criteria
            
        Note:
            Returns empty list if required filter is missing for the selected mode.
        """
        stmt = select(Property)

        if self.mode == "bounds":
            if not self.bounds:
                return []
            b = self.bounds
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
        elif self.mode == "polygon":
            if not self.polygon:
                return []
            geojson_str = json.dumps(self.polygon.geojson)
            geom = func.ST_GeomFromGeoJSON(geojson_str)
            stmt = stmt.where(func.ST_Within(Property.location, geom))

        stmt = stmt.limit(self.limit)

        results = db.execute(stmt).scalars().all()
        return [PropertySearchResult.from_orm_obj(p) for p in results]


class PropertyListResponse(BaseModel):
    """
    Schema for property list API response.
    
    Standard response format for property listing endpoints,
    containing the list of properties and total count.
    
    Attributes:
        items: List of property search results
        total: Total number of properties in the result set
    """
    items: list[PropertySearchResult]
    total: int


