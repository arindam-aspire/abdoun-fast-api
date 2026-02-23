from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.property import Property
from app.schemas.property import (
    PropertyDetail,
    PropertySearchResult,
    PropertyListResponse,
    PropertySearchResultExtended,
    PropertyListResponseExtended,
    PropertySearchResponse,
)
from app.utils.constants import ErrorMessages, Defaults
from app.utils.status_codes import STATUS_NOT_FOUND
 
router = APIRouter()

DBSessionDep = Annotated[Session, Depends(get_db)]


@router.get("", response_model=PropertySearchResponse)
def list_properties(
    db: DBSessionDep,
    status: Optional[str] = Query(None, description="Listing type: buy or rent"),
    category: Optional[str] = Query(None, description="One of: residential, commercial, land. On Hero, 'Land' is sent as lands."),
    type: Optional[str] = Query(None, description="Slugified property type (e.g., apartments, villas, residential-lands)"),
    city: Optional[str] = Query(None, description="City name, lowercase"),
    locations: Optional[str] = Query(None, description="Comma-separated area/neighborhood names, lowercase"),
    budgetMin: Optional[str] = Query(None, description="Minimum price in JD (numeric string)"),
    budgetMax: Optional[str] = Query(None, description="Maximum price in JD (numeric string)"),
    minPrice: Optional[str] = Query(None, description="Alias for budgetMin (for hero search compatibility)"),
    maxPrice: Optional[str] = Query(None, description="Alias for budgetMax (for hero search compatibility)"),
    page: int = Query(1, ge=1, description="Page number, 1-based"),
    pageSize: int = Query(12, ge=1, le=100, description="Items per page"),
) -> PropertySearchResponse:
    """
    Search properties with optional filters and pagination.
    
    Matches the frontend search contract for Home Page and Search Results page.
    Supports both budgetMin/budgetMax and minPrice/maxPrice for compatibility.
    """
    stmt = select(Property)
    
    # Apply filters
    filters = []
    
    # Status filter (buy = has selling_price, rent = has rent_price)
    if status:
        status_lower = status.lower()
        if status_lower == "buy":
            filters.append(Property.selling_price_amount.isnot(None))
        elif status_lower == "rent":
            filters.append(Property.rent_price_amount.isnot(None))
    
    # Filter by category
    if category:
        category_lower = category.lower()
        # Handle "lands" as alias for "land"
        if category_lower in ("land", "lands"):
            filters.append(func.lower(Property.category).contains("land"))
        elif category_lower == "residential":
            filters.append(
                or_(
                    func.lower(Property.category).contains("apartment"),
                    func.lower(Property.category).contains("villa"),
                    func.lower(Property.category).contains("house"),
                    func.lower(Property.category).contains("building"),
                    func.lower(Property.category).contains("farm"),
                )
            )
        elif category_lower == "commercial":
            filters.append(
                or_(
                    func.lower(Property.category).contains("office"),
                    func.lower(Property.category).contains("showroom"),
                    func.lower(Property.category).contains("warehouse"),
                    func.lower(Property.category).contains("business"),
                )
            )
        else:
            filters.append(func.lower(Property.category).contains(category_lower))
    
    # Filter by type (property type slug)
    if type:
        type_lower = type.lower().replace("-", " ")
        # Residential types
        if "apartment" in type_lower:
            filters.append(func.lower(Property.category).contains("apartment"))
        elif "villa" in type_lower:
            filters.append(
                or_(
                    func.lower(Property.category).contains("villa"),
                    func.lower(Property.category).contains("house"),
                )
            )
        elif "building" in type_lower:
            filters.append(func.lower(Property.category).contains("building"))
        elif "farm" in type_lower:
            filters.append(func.lower(Property.category).contains("farm"))
        # Commercial types
        elif "office" in type_lower:
            filters.append(func.lower(Property.category).contains("office"))
        elif "showroom" in type_lower:
            filters.append(func.lower(Property.category).contains("showroom"))
        elif "warehouse" in type_lower:
            filters.append(func.lower(Property.category).contains("warehouse"))
        elif "business" in type_lower:
            filters.append(func.lower(Property.category).contains("business"))
        # Land types
        elif "land" in type_lower:
            filters.append(func.lower(Property.category).contains("land"))
        else:
            filters.append(func.lower(Property.category).contains(type_lower))
    
    # Filter by city (search in location_name)
    if city:
        city_lower = city.lower()
        filters.append(func.lower(Property.location_name).contains(city_lower))
    
    # Filter by locations (comma-separated areas/neighborhoods)
    if locations:
        location_list = [loc.strip().lower() for loc in locations.split(",") if loc.strip()]
        if location_list:
            location_filters = [
                func.lower(Property.location_name).contains(loc) for loc in location_list
            ]
            filters.append(or_(*location_filters))
    
    # Filter by budget (price range)
    # Support both budgetMin/budgetMax and minPrice/maxPrice
    min_budget = budgetMin or minPrice
    max_budget = budgetMax or maxPrice
    
    # Determine which price field to filter based on status
    status_lower = (status or "").lower() if status else None
    
    if min_budget:
        try:
            min_val = float(min_budget)
            if status_lower == "buy":
                filters.append(Property.selling_price_amount >= min_val)
            elif status_lower == "rent":
                filters.append(Property.rent_price_amount >= min_val)
            else:
                # No status specified - check both price fields
                filters.append(
                    or_(
                        Property.selling_price_amount >= min_val,
                        Property.rent_price_amount >= min_val,
                    )
                )
        except (ValueError, TypeError):
            pass  # Ignore invalid budget values
    
    if max_budget:
        try:
            max_val = float(max_budget)
            if status_lower == "buy":
                filters.append(Property.selling_price_amount <= max_val)
            elif status_lower == "rent":
                filters.append(Property.rent_price_amount <= max_val)
            else:
                # No status specified - check both price fields
                filters.append(
                    or_(
                        Property.selling_price_amount <= max_val,
                        Property.rent_price_amount <= max_val,
                    )
                )
        except (ValueError, TypeError):
            pass  # Ignore invalid budget values
    
    # Apply all filters
    if filters:
        stmt = stmt.where(and_(*filters))
    
    # Get total count before pagination
    count_stmt = select(func.count(Property.id))
    if filters:
        count_stmt = count_stmt.where(and_(*filters))
    total = db.execute(count_stmt).scalar() or 0
    
    # Calculate offset from page and pageSize
    offset = (page - 1) * pageSize
    
    # Apply ordering and pagination
    stmt = stmt.order_by(Property.created_at.desc()).offset(offset).limit(pageSize)
    
    # Execute query
    results = db.execute(stmt).scalars().all()
    
    # Convert to extended format
    data = [
        PropertySearchResultExtended.from_orm_obj(p)
        for p in results
    ]
    
    return PropertySearchResponse(
        data=data,
        total=total,
        page=page,
        pageSize=pageSize
    )


@router.get("/{property_id}/similar", response_model=PropertySearchResponse)
def get_similar_properties(
    property_id: int,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=50, description="Maximum number of similar properties to return"),
) -> PropertySearchResponse:
    """
    Get similar properties based on the selected property.
    
    Similarity is determined by:
    - Same category/type
    - Same city/location
    - Similar price range (±20%)
    - Similar number of bedrooms/bathrooms
    - Similar built-up area
    
    Args:
        property_id: The unique identifier of the property to find similar ones for
        limit: Maximum number of similar properties to return (default: 20, max: 50)
        
    Returns:
        PropertySearchResponse with similar properties
        
    Raises:
        HTTPException: 404 if property not found
    """
    # Get the reference property
    prop = db.get(Property, property_id)
    if not prop:
        raise HTTPException(
            status_code=STATUS_NOT_FOUND,
            detail=ErrorMessages.PROPERTY_NOT_FOUND
        )
    
    # Build similarity filters
    filters = []
    
    # Exclude the current property
    filters.append(Property.id != property_id)
    
    # Same category/type
    if prop.category:
        filters.append(Property.category.ilike(f"%{prop.category}%"))
    
    # Same city (extract from location_name if available)
    if prop.location_name:
        # Try to extract city (usually after " - " separator)
        location_parts = prop.location_name.split(" - ")
        if len(location_parts) >= 2:
            city = location_parts[-1].strip()
            filters.append(Property.location_name.ilike(f"%{city}%"))
        else:
            # If no separator, use the whole location_name
            filters.append(Property.location_name.ilike(f"%{prop.location_name}%"))
    
    # Similar price range (±20%)
    price_tolerance = 0.2  # 20% tolerance
    
    # Check if property has selling price or rent price
    if prop.selling_price_amount:
        price = float(prop.selling_price_amount)
        min_price = price * (1 - price_tolerance)
        max_price = price * (1 + price_tolerance)
        filters.append(
            and_(
                Property.selling_price_amount.isnot(None),
                Property.selling_price_amount >= min_price,
                Property.selling_price_amount <= max_price,
            )
        )
    elif prop.rent_price_amount:
        price = float(prop.rent_price_amount)
        min_price = price * (1 - price_tolerance)
        max_price = price * (1 + price_tolerance)
        filters.append(
            and_(
                Property.rent_price_amount.isnot(None),
                Property.rent_price_amount >= min_price,
                Property.rent_price_amount <= max_price,
            )
        )
    
    # Similar bedrooms (±1)
    if prop.bedrooms:
        filters.append(
            or_(
                Property.bedrooms == prop.bedrooms,
                Property.bedrooms == prop.bedrooms - 1,
                Property.bedrooms == prop.bedrooms + 1,
            )
        )
    
    # Similar bathrooms (±1)
    if prop.bathrooms:
        filters.append(
            or_(
                Property.bathrooms == prop.bathrooms,
                Property.bathrooms == prop.bathrooms - 1,
                Property.bathrooms == prop.bathrooms + 1,
            )
        )
    
    # Similar area (±20%)
    if prop.built_up_area:
        area = float(prop.built_up_area)
        min_area = area * (1 - price_tolerance)
        max_area = area * (1 + price_tolerance)
        filters.append(
            and_(
                Property.built_up_area.isnot(None),
                Property.built_up_area >= min_area,
                Property.built_up_area <= max_area,
            )
        )
    
    # Build query
    stmt = select(Property)
    if filters:
        stmt = stmt.where(and_(*filters))
    
    # Order by relevance (same category first, then by price similarity, then by creation date)
    stmt = stmt.order_by(Property.created_at.desc()).limit(limit)
    
    # Execute query
    results = db.execute(stmt).scalars().all()
    
    # Convert to extended format
    data = [
        PropertySearchResultExtended.from_orm_obj(p)
        for p in results
    ]
    
    return PropertySearchResponse(
        data=data,
        total=len(data),
        page=1,
        pageSize=len(data)
    )


@router.get("/{property_id}", response_model=PropertyDetail)
def get_property(
    property_id: int,
    db: DBSessionDep,
) -> PropertyDetail:
    """
    Get detailed information about a specific property.
    
    Args:
        property_id: The unique identifier of the property
        
    Returns:
        PropertyDetail with all property information
        
    Raises:
        HTTPException: 404 if property not found
    """
    prop = db.get(Property, property_id)
    if not prop:
        raise HTTPException(
            status_code=STATUS_NOT_FOUND,
            detail=ErrorMessages.PROPERTY_NOT_FOUND
        )
    return PropertyDetail.from_orm_obj(prop)

