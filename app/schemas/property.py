"""
Property schemas for API request/response models.

This module defines Pydantic models for property-related API operations,
including search results, property details, search requests, and responses.
"""

from __future__ import annotations

from typing import Any, Literal, Optional
import json
import hashlib

from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session

import uuid
from app.models.property_normalized import PropertyNormalized as Property
from app.utils.constants import Defaults


def uuid_to_int_hash(uuid_obj: uuid.UUID) -> int:
    """
    Convert a UUID to a deterministic integer hash.
    
    Uses SHA256 to ensure deterministic hashing across different Python processes.
    
    Args:
        uuid_obj: UUID object to convert
        
    Returns:
        Integer hash value (0 to 10^9 - 1)
    """
    # Use SHA256 for deterministic hashing
    hash_bytes = hashlib.sha256(str(uuid_obj).encode()).digest()
    # Convert first 8 bytes to integer and take modulo
    hash_int = int.from_bytes(hash_bytes[:8], byteorder='big')
    return hash_int % (10**9)


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
        
        Supports both old Property model and new PropertyNormalized model.
        
        Args:
            obj: Property database model instance
            
        Returns:
            PropertySearchResult instance with data from the ORM object
        """
        # Handle normalized model (PropertyNormalized)
        if hasattr(obj, 'category_id'):  # Normalized model
            price = obj.selling_price_amount or obj.rent_price_amount
            currency = obj.selling_price_currency or obj.rent_price_currency
            # Parse images from JSON string
            images = []
            if obj.images:
                try:
                    import json
                    images = json.loads(obj.images) if isinstance(obj.images, str) else obj.images
                except:
                    images = []
            thumbnail = images[0] if images else None
            # Convert UUID to int for compatibility (use deterministic hash)
            prop_id = uuid_to_int_hash(obj.id) if isinstance(obj.id, uuid.UUID) else int(obj.id) if hasattr(obj.id, '__int__') else obj.id
        else:  # Old model
            price = obj.selling_price_amount or obj.rent_price_amount
            currency = obj.selling_price_currency or obj.rent_price_currency
            thumbnail = (obj.images or [None])[0]
            prop_id = obj.id
        
        # Handle "nan" titles
        title = obj.title if obj.title and str(obj.title).lower() not in ("nan", "none") else Defaults.UNTITLED_PROPERTY
        return cls(
            id=prop_id,
            title=title,
            price=float(price) if price is not None else None,
            price_currency=currency,
            bedrooms=obj.bedrooms,
            bathrooms=obj.bathrooms,
            thumbnail=thumbnail,
            lat=float(obj.latitude) if obj.latitude is not None else None,
            lng=float(obj.longitude) if obj.longitude is not None else None,
        )


class PropertySearchResultExtended(BaseModel):
    """
    Extended schema for property search results matching frontend format.
    
    Attributes match the expected JSON format for search results.
    """
    id: int | str  # Support both int (old) and UUID string (normalized)
    title: str
    price: Optional[str] = None  # Formatted as "2,100 JD"
    status: Optional[str] = None  # "rent" or "buy"
    category: Optional[str] = None  # "residential", "land", etc.
    searchPropertyType: Optional[str] = None  # "Apartments", "Residential Lands"
    city: Optional[str] = None  # "Amman"
    areaName: Optional[str] = None  # "Jabal Amman", "Swefieh"
    propertyType: Optional[str] = None  # "Apartment", "Lot / Land for sale"
    images: Optional[list[str]] = None
    location: Optional[str] = None  # "Jabal Amman, Amman"
    beds: Optional[int] = None
    baths: Optional[int] = None
    area: Optional[str] = None  # Formatted as "1,800"
    acres: Optional[str] = None  # For land properties
    highlights: Optional[str] = None
    badges: Optional[list[str]] = None
    handover: Optional[str] = None
    paymentPlan: Optional[str] = None
    validatedDate: Optional[str] = None
    brokerName: Optional[str] = None
    brokerLogo: Optional[str] = None

    @classmethod
    def from_orm_obj(cls, obj: Property) -> "PropertySearchResultExtended":
        """
        Create PropertySearchResultExtended from a Property ORM object.
        
        Args:
            obj: Property database model instance
            
        Returns:
            PropertySearchResultExtended instance with formatted data
        """
        # Parse location_name to extract city and areaName
        # Handle normalized model (has relationships) vs old model
        city = None
        areaName = None
        if hasattr(obj, 'city_id'):  # Normalized model - use relationships
            city = obj.city.name if obj.city else None
            areaName = obj.area_rel.name if obj.area_rel else None
        # Fallback to location_name parsing if relationships not loaded
        if not city or not areaName:
            if obj.location_name:
                parts = obj.location_name.split(" - ")
                if len(parts) >= 2:
                    areaName = areaName or parts[0].strip()
                    city = city or parts[-1].strip()
                elif len(parts) == 1:
                    city = city or parts[0].strip()
        
        # Determine status (buy or rent)
        # Priority: if both exist, status is "buy" (for API compatibility)
        # But badges will show both "For Sale" and "For Rent"
        status = None
        has_selling_price = obj.selling_price_amount is not None
        has_rent_price = obj.rent_price_amount is not None
        
        if has_selling_price:
            status = "buy"
        elif has_rent_price:
            status = "rent"
        
        # Format price (prefer selling price if both exist)
        price_str = None
        if obj.selling_price_amount:
            price_val = float(obj.selling_price_amount)
            currency = obj.selling_price_currency or "JD"
            if price_val == int(price_val):
                price_str = f"{int(price_val):,} {currency}"
            else:
                price_str = f"{price_val:,.2f} {currency}"
        elif obj.rent_price_amount:
            price_val = float(obj.rent_price_amount)
            currency = obj.rent_price_currency or "JD"
            if price_val == int(price_val):
                price_str = f"{int(price_val):,} {currency}"
            else:
                price_str = f"{price_val:,.2f} {currency}"
        
        # Format area - handle both old and normalized models
        area_str = None
        built_up_area = getattr(obj, 'built_up_area', None) or getattr(obj, 'area', None)
        if built_up_area:
            area_val = float(built_up_area)
            if area_val == int(area_val):
                area_str = f"{int(area_val):,}"
            else:
                area_str = f"{area_val:,.2f}"
        
        # Map category to searchPropertyType and propertyType
        # Handle normalized model (has relationships) vs old model (has direct fields)
        searchPropertyType = None
        propertyType = None
        if hasattr(obj, 'category_id'):  # Normalized model
            # Access via relationships
            category_name = obj.category.name if obj.category else None
            type_name = obj.type.name if obj.type else None
            city_name = obj.city.name if obj.city else None
            area_name = obj.area_rel.name if obj.area_rel else None
            category_lower = (category_name or "").lower()
        else:  # Old model
            category_name = getattr(obj, 'category', None)
            category_lower = (category_name or "").lower()
            city_name = None
            area_name = None
        
        if "apartment" in category_lower:
            searchPropertyType = "Apartments"
            propertyType = "Apartment"
            category = "residential"
        elif "villa" in category_lower or "house" in category_lower:
            searchPropertyType = "Villas"
            propertyType = "Villa"
            category = "residential"
        elif "building" in category_lower and "land" not in category_lower:
            searchPropertyType = "Buildings"
            propertyType = "Building"
            category = "residential"
        elif "farm" in category_lower:
            searchPropertyType = "Farms"
            propertyType = "Farm"
            category = "residential"
        elif "office" in category_lower:
            searchPropertyType = "Offices"
            propertyType = "Office"
            category = "commercial"
        elif "showroom" in category_lower:
            searchPropertyType = "Showrooms"
            propertyType = "Showroom"
            category = "commercial"
        elif "warehouse" in category_lower:
            searchPropertyType = "Warehouses"
            propertyType = "Warehouse"
            category = "commercial"
        elif "business" in category_lower:
            searchPropertyType = "Businesses"
            propertyType = "Business"
            category = "commercial"
        elif "land" in category_lower:
            # Determine land type
            if "residential" in category_lower:
                searchPropertyType = "Residential Lands"
            elif "commercial" in category_lower:
                searchPropertyType = "Commercial Lands"
            elif "industrial" in category_lower:
                searchPropertyType = "Industrial Lands"
            elif "agricultural" in category_lower:
                searchPropertyType = "Agricultural Lands"
            elif "mixed" in category_lower or "use" in category_lower:
                searchPropertyType = "Mixed-Use Lands"
            else:
                searchPropertyType = "Residential Lands"  # Default for land
            propertyType = "Lot / Land for sale"
            category = "land"
        else:
            category = "residential"  # Default
            # Use type_name if available, otherwise category_name, otherwise default
            if hasattr(obj, 'category_id'):  # Normalized model
                if type_name:
                    propertyType = type_name
                    searchPropertyType = type_name + "s" if not type_name.endswith("s") else type_name
                elif category_name:
                    propertyType = category_name
                    searchPropertyType = category_name
                else:
                    propertyType = "Property"
                    searchPropertyType = "Properties"
            else:  # Old model
                if category_name:
                    propertyType = category_name
                    searchPropertyType = category_name
                else:
                    propertyType = "Property"
                    searchPropertyType = "Properties"
        
        # Create highlights
        highlights_parts = []
        if obj.bedrooms:
            highlights_parts.append(f"{obj.bedrooms}BHK")
        # Get category name from relationship or direct field
        category_for_highlights = None
        if hasattr(obj, 'category_id'):  # Normalized
            category_for_highlights = obj.category.name if obj.category else None
        else:  # Old model
            category_for_highlights = getattr(obj, 'category', None)
        if category_for_highlights:
            highlights_parts.append(category_for_highlights)
        highlights = " | ".join(highlights_parts) if highlights_parts else None
        
        # Create badges
        # Show both badges if both prices exist
        badges = []
        if has_selling_price:
            badges.append("For Sale")
        if has_rent_price:
            badges.append("For Rent")
        # Check verification status - handle both old and normalized models
        is_verified = False
        if hasattr(obj, 'is_verified'):  # Normalized model
            is_verified = obj.is_verified
        elif hasattr(obj, 'status'):  # Old model
            is_verified = obj.status and obj.status.lower() == "ok"
        if is_verified:
            badges.append("Verified")
        
        # Handle "nan" titles
        title = obj.title if obj.title and str(obj.title).lower() not in ("nan", "none") else Defaults.UNTITLED_PROPERTY
        
        # Format validated date from created_at if available
        validated_date_str = None
        if obj.created_at:
            day = obj.created_at.day
            suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
            validated_date_str = f"{day}{suffix} of {obj.created_at.strftime('%B')}"
        
        # Parse images - handle both JSON string (normalized) and list (old)
        images_list = []
        if hasattr(obj, 'images'):
            if isinstance(obj.images, str):
                try:
                    import json
                    images_list = json.loads(obj.images)
                except:
                    images_list = []
            elif isinstance(obj.images, list):
                images_list = obj.images
        
        # Convert UUID to int for compatibility
        prop_id = obj.id
        if hasattr(obj, 'category_id'):  # Normalized model with UUID
            # Convert UUID to int hash for API compatibility
            if isinstance(obj.id, uuid.UUID):
                prop_id = uuid_to_int_hash(obj.id)
            elif hasattr(obj.id, '__int__'):
                prop_id = int(obj.id)
        
        return cls(
            id=prop_id,
            title=title,
            price=price_str,
            status=status,
            category=category,
            searchPropertyType=searchPropertyType,
            city=city,
            areaName=areaName,
            propertyType=propertyType,
            images=images_list,
            location=obj.location_name,
            beds=obj.bedrooms or 0,
            baths=obj.bathrooms or 0,
            area=area_str,
            acres=None,  # Could be calculated if needed
            highlights=highlights,
            badges=badges if badges else None,
            handover=None,  # Not available in current data model
            paymentPlan=None,  # Not available in current data model
            validatedDate=validated_date_str,
            brokerName="Abdoun Real Estate",  # Default broker name
            brokerLogo=None,  # Not available in current data model
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
    more_features: Optional[dict[str, Any]] = None  # JSON object with key-value pairs
    images: Optional[list[str]] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None

    @classmethod
    def from_orm_obj(cls, obj: Property) -> "PropertyDetail":
        """
        Create PropertyDetail from a Property ORM object.
        
        Supports both old Property model and new PropertyNormalized model.
        
        Args:
            obj: Property database model instance
            
        Returns:
            PropertyDetail instance with data from the ORM object
        """
        # Handle "nan" titles
        title = obj.title if obj.title and str(obj.title).lower() not in ("nan", "none") else Defaults.UNTITLED_PROPERTY
        
        # Handle normalized model vs old model
        if hasattr(obj, 'category_id'):  # Normalized model
            # Get category and status from relationships
            category_name = obj.category.name if obj.category else None
            status_name = obj.property_status.name if obj.property_status else None
            
            # Parse images from JSON string
            images_list = []
            if obj.images:
                try:
                    import json
                    images_list = json.loads(obj.images) if isinstance(obj.images, str) else obj.images
                except:
                    images_list = []
            
            # Get features from relationship
            features_list = [f.feature.name for f in obj.features if f.feature] if obj.features else []
            # Get more_features from JSON column (already in key-value format as dict)
            more_features_dict = obj.more_features if hasattr(obj, 'more_features') and obj.more_features else None
            
            # Convert UUID to int for compatibility
            prop_id = obj.id
            if isinstance(obj.id, uuid.UUID):
                prop_id = uuid_to_int_hash(obj.id)
            
            built_up_area = float(obj.area) if obj.area is not None else None
        else:  # Old model
            category_name = getattr(obj, 'category', None)
            status_name = getattr(obj, 'status', None)
            images_list = obj.images or []
            features_list = obj.features or []
            more_features_list = obj.more_features or []
            prop_id = obj.id
            built_up_area = float(obj.built_up_area) if obj.built_up_area is not None else None
        
        return cls(
            id=prop_id,
            url=obj.url,
            title=title,
            description=obj.description,
            category=category_name,
            status=status_name,
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
            built_up_area=built_up_area,
            features=features_list,
            more_features=more_features_dict if hasattr(obj, 'category_id') else more_features_list,
            images=images_list,
            latitude=float(obj.latitude) if obj.latitude is not None else None,
            longitude=float(obj.longitude) if obj.longitude is not None else None,
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
        
        Supports both old Property model and new PropertyNormalized model.
        
        Args:
            db: SQLAlchemy database session
            
        Returns:
            List of PropertySearchResult objects matching the search criteria
            
        Note:
            Returns empty list if required filter is missing for the selected mode.
        """
        from sqlalchemy.orm import joinedload
        from app.models.property_normalized import PropertyCategory, PropertyType, City, Area
        
        stmt = select(Property).options(
            joinedload(Property.category),
            joinedload(Property.type),
            joinedload(Property.city),
            joinedload(Property.area_rel),
        )

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

        results = db.execute(stmt).unique().scalars().all()
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


class PropertyListResponseExtended(BaseModel):
    """
    Extended schema for property list API response with frontend format.
    
    Attributes:
        items: List of extended property search results
        total: Total number of properties in the result set
    """
    items: list[PropertySearchResultExtended]
    total: int


class PropertySearchResponse(BaseModel):
    """
    Search API response matching the exact frontend contract.
    
    Attributes:
        data: List of property search results
        total: Total number of properties matching filters
        page: Current page number (1-based)
        pageSize: Number of items per page
    """
    data: list[PropertySearchResultExtended]
    total: int
    page: int
    pageSize: int


