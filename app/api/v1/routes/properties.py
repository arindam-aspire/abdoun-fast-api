from typing import Annotated, Optional
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.property_normalized import (
    PropertyNormalized as Property,
    PropertyCategory,
    PropertyType,
    City,
    Area,
    PropertyFeature,
)
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
from sqlalchemy.orm import joinedload
 
router = APIRouter()
logger = logging.getLogger(__name__)

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
    exclusive: Optional[str] = Query(None, description="Filter by exclusive status (true/1 for exclusive only, false/0 for non-exclusive only)"),
    page: int = Query(1, ge=1, description="Page number, 1-based"),
    pageSize: int = Query(12, ge=1, le=100, description="Items per page"),
    lang: Optional[str] = Query(None, description="Language code for title/description: en, ar, esp, fr"),
) -> PropertySearchResponse:
    """
    Search properties with optional filters and pagination.
    
    Matches the frontend search contract for Home Page and Search Results page.
    Supports both budgetMin/budgetMax and minPrice/maxPrice for compatibility.
    """
    # Build query with joins for normalized model (include translations for multi-lang title/description)
    stmt = select(Property).options(
        joinedload(Property.category),
        joinedload(Property.type),
        joinedload(Property.city),
        joinedload(Property.area_rel),
        joinedload(Property.property_status),
        joinedload(Property.translations),
    )
    
    # Join tables for filtering
    stmt = stmt.join(PropertyCategory, Property.category_id == PropertyCategory.id)
    stmt = stmt.join(PropertyType, Property.type_id == PropertyType.id)
    stmt = stmt.join(City, Property.city_id == City.id)
    stmt = stmt.join(Area, Property.location_id == Area.id)
    
    # Apply filters
    filters = []
    
    # Status filter (buy = has selling_price, rent = has rent_price)
    if status:
        status_lower = status.lower()
        if status_lower == "buy":
            filters.append(Property.selling_price_amount.isnot(None))
        elif status_lower == "rent":
            filters.append(Property.rent_price_amount.isnot(None))
    
    # Filter by category - use joined PropertyCategory table
    if category:
        category_lower = category.lower()
        # Handle "lands" as alias for "land"
        if category_lower in ("land", "lands"):
            filters.append(func.lower(PropertyCategory.name).contains("land"))
        elif category_lower == "residential":
            filters.append(
                or_(
                    func.lower(PropertyCategory.name).contains("residential"),
                    func.lower(PropertyType.name).contains("apartment"),
                    func.lower(PropertyType.name).contains("villa"),
                    func.lower(PropertyType.name).contains("house"),
                    func.lower(PropertyType.name).contains("building"),
                    func.lower(PropertyType.name).contains("farm"),
                )
            )
        elif category_lower == "commercial":
            filters.append(
                or_(
                    func.lower(PropertyCategory.name).contains("commercial"),
                    func.lower(PropertyType.name).contains("office"),
                    func.lower(PropertyType.name).contains("showroom"),
                    func.lower(PropertyType.name).contains("warehouse"),
                    func.lower(PropertyType.name).contains("business"),
                )
            )
        else:
            filters.append(func.lower(PropertyCategory.name).contains(category_lower))
    
    # Filter by type (property type slug) - use joined PropertyType table
    if type:
        type_lower = type.lower().replace("-", " ")
        # Residential types
        if "apartment" in type_lower:
            filters.append(func.lower(PropertyType.name).contains("apartment"))
        elif "villa" in type_lower:
            filters.append(
                or_(
                    func.lower(PropertyType.name).contains("villa"),
                    func.lower(PropertyType.name).contains("house"),
                )
            )
        elif "building" in type_lower:
            filters.append(func.lower(PropertyType.name).contains("building"))
        elif "farm" in type_lower:
            filters.append(func.lower(PropertyType.name).contains("farm"))
        # Commercial types
        elif "office" in type_lower:
            filters.append(func.lower(PropertyType.name).contains("office"))
        elif "showroom" in type_lower:
            filters.append(func.lower(PropertyType.name).contains("showroom"))
        elif "warehouse" in type_lower:
            filters.append(func.lower(PropertyType.name).contains("warehouse"))
        elif "business" in type_lower:
            filters.append(func.lower(PropertyType.name).contains("business"))
        # Land types
        elif "land" in type_lower:
            filters.append(func.lower(PropertyType.name).contains("land"))
        else:
            filters.append(func.lower(PropertyType.name).contains(type_lower))
    
    # Filter by city - use joined City table or location_name fallback
    if city:
        city_lower = city.lower()
        filters.append(
            or_(
                func.lower(City.name).contains(city_lower),
                func.lower(Property.location_name).contains(city_lower)
            )
        )
    
    # Filter by locations (comma-separated areas/neighborhoods) - use joined Area table
    if locations:
        location_list = [loc.strip().lower() for loc in locations.split(",") if loc.strip()]
        if location_list:
            location_filters = [
                or_(
                    func.lower(Area.name).contains(loc),
                    func.lower(Property.location_name).contains(loc)
                ) for loc in location_list
            ]
            filters.append(or_(*location_filters))
    
    # Filter by exclusive status
    exclusive_bool = None
    if exclusive is not None:
        # Handle string "true"/"false" or boolean True/False
        exclusive_bool = str(exclusive).lower() in ("true", "1", "yes")
        if exclusive_bool:
            filters.append(Property.is_exclusive == True)
        else:
            filters.append(Property.is_exclusive == False)
    
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
    # Need to join tables for count query if filters use them
    count_stmt = select(func.count(Property.id))
    # Add joins if we have category/type/city/location filters
    if category or type or city or locations:
        count_stmt = count_stmt.join(PropertyCategory, Property.category_id == PropertyCategory.id)
        count_stmt = count_stmt.join(PropertyType, Property.type_id == PropertyType.id)
        count_stmt = count_stmt.join(City, Property.city_id == City.id)
        count_stmt = count_stmt.join(Area, Property.location_id == Area.id)
    if filters:
        count_stmt = count_stmt.where(and_(*filters))
    total = db.execute(count_stmt).scalar() or 0
    
    # Calculate offset from page and pageSize
    offset = (page - 1) * pageSize
    
    # Apply ordering and pagination
    stmt = stmt.order_by(Property.created_at.desc()).offset(offset).limit(pageSize)
    
    # Execute query - use unique() to avoid duplicate rows from joined eager loads
    results = db.execute(stmt).unique().scalars().all()
    
    # Convert to extended format
    data = [
        PropertySearchResultExtended.from_orm_obj(p, lang=lang)
        for p in results
    ]
    
    return PropertySearchResponse(
        data=data,
        total=total,
        page=page,
        pageSize=pageSize
    )


@router.get("/exclusive", response_model=PropertySearchResponse)
def list_exclusive_properties(
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
    lang: Optional[str] = Query(None, description="Language code for title/description: en, ar, esp, fr"),
) -> PropertySearchResponse:
    """
    List exclusive properties with optional filters and pagination.
    
    Same as regular property list endpoint but only returns properties where is_exclusive = True.
    Uses the same response format and supports all the same filters.
    """
    # Build query with joins for normalized model (same as list_properties; include translations)
    stmt = select(Property).options(
        joinedload(Property.category),
        joinedload(Property.type),
        joinedload(Property.city),
        joinedload(Property.area_rel),
        joinedload(Property.property_status),
        joinedload(Property.translations),
    )
    
    # Join tables for filtering
    stmt = stmt.join(PropertyCategory, Property.category_id == PropertyCategory.id)
    stmt = stmt.join(PropertyType, Property.type_id == PropertyType.id)
    stmt = stmt.join(City, Property.city_id == City.id)
    stmt = stmt.join(Area, Property.location_id == Area.id)
    
    # Apply filters (same logic as list_properties)
    filters = []
    
    # CRITICAL: Only show exclusive properties
    filters.append(Property.is_exclusive == True)
    
    # Status filter (buy = has selling_price, rent = has rent_price)
    if status:
        status_lower = status.lower()
        if status_lower == "buy":
            filters.append(Property.selling_price_amount.isnot(None))
        elif status_lower == "rent":
            filters.append(Property.rent_price_amount.isnot(None))
    
    # Filter by category - use joined PropertyCategory table
    if category:
        category_lower = category.lower()
        # Handle "lands" as alias for "land"
        if category_lower in ("land", "lands"):
            filters.append(func.lower(PropertyCategory.name).contains("land"))
        elif category_lower == "residential":
            filters.append(
                or_(
                    func.lower(PropertyCategory.name).contains("residential"),
                    func.lower(PropertyType.name).contains("apartment"),
                    func.lower(PropertyType.name).contains("villa"),
                    func.lower(PropertyType.name).contains("house"),
                    func.lower(PropertyType.name).contains("building"),
                    func.lower(PropertyType.name).contains("farm"),
                )
            )
        elif category_lower == "commercial":
            filters.append(
                or_(
                    func.lower(PropertyCategory.name).contains("commercial"),
                    func.lower(PropertyType.name).contains("office"),
                    func.lower(PropertyType.name).contains("showroom"),
                    func.lower(PropertyType.name).contains("warehouse"),
                    func.lower(PropertyType.name).contains("business"),
                )
            )
        else:
            filters.append(func.lower(PropertyCategory.name).contains(category_lower))
    
    # Filter by type (property type slug) - use joined PropertyType table
    if type:
        type_lower = type.lower().replace("-", " ")
        # Residential types
        if "apartment" in type_lower:
            filters.append(func.lower(PropertyType.name).contains("apartment"))
        elif "villa" in type_lower:
            filters.append(
                or_(
                    func.lower(PropertyType.name).contains("villa"),
                    func.lower(PropertyType.name).contains("house"),
                )
            )
        elif "building" in type_lower:
            filters.append(func.lower(PropertyType.name).contains("building"))
        elif "farm" in type_lower:
            filters.append(func.lower(PropertyType.name).contains("farm"))
        # Commercial types
        elif "office" in type_lower:
            filters.append(func.lower(PropertyType.name).contains("office"))
        elif "showroom" in type_lower:
            filters.append(func.lower(PropertyType.name).contains("showroom"))
        elif "warehouse" in type_lower:
            filters.append(func.lower(PropertyType.name).contains("warehouse"))
        else:
            filters.append(func.lower(PropertyType.name).contains(type_lower))
    
    # Filter by city - use joined City table
    if city:
        city_lower = city.lower()
        filters.append(
            or_(
                func.lower(City.name).contains(city_lower),
                func.lower(Property.location_name).contains(city_lower)
            )
        )
    
    # Filter by locations (comma-separated areas/neighborhoods) - use joined Area table
    if locations:
        location_list = [loc.strip().lower() for loc in locations.split(",") if loc.strip()]
        if location_list:
            location_filters = [
                or_(
                    func.lower(Area.name).contains(loc),
                    func.lower(Property.location_name).contains(loc)
                ) for loc in location_list
            ]
            filters.append(or_(*location_filters))
    
    # Note: is_exclusive == True filter is already applied at line 301
    
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
    # Need to join tables for count query if filters use them
    count_stmt = select(func.count(Property.id))
    # Add joins if we have category/type/city/location filters
    if category or type or city or locations:
        count_stmt = count_stmt.join(PropertyCategory, Property.category_id == PropertyCategory.id)
        count_stmt = count_stmt.join(PropertyType, Property.type_id == PropertyType.id)
        count_stmt = count_stmt.join(City, Property.city_id == City.id)
        count_stmt = count_stmt.join(Area, Property.location_id == Area.id)
    if filters:
        count_stmt = count_stmt.where(and_(*filters))
    total = db.execute(count_stmt).scalar() or 0
    
    # Calculate offset from page and pageSize
    offset = (page - 1) * pageSize
    
    # Apply ordering and pagination
    stmt = stmt.order_by(Property.created_at.desc()).offset(offset).limit(pageSize)
    
    # Execute query - use unique() to avoid duplicate rows from joined eager loads
    results = db.execute(stmt).unique().scalars().all()

    # Convert to extended format
    data = [
        PropertySearchResultExtended.from_orm_obj(p, lang=lang)
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
    property_id: str,  # FastAPI path params are always strings
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=50, description="Maximum number of similar properties to return"),
    lang: Optional[str] = Query(None, description="Language code for title/description: en, ar, esp, fr"),
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
    # Get the reference property with relationships loaded
    # Handle UUID lookup - property_id might be int (from hash) or UUID string
    prop = None
    import uuid
    from app.schemas.property import uuid_to_int_hash
    
    # Try to parse as UUID first
    try:
        uuid_obj = uuid.UUID(property_id)
        prop = db.get(Property, uuid_obj)
        if prop:
            # Reload with relationships
            prop = db.execute(
                select(Property)
                .options(
                    joinedload(Property.category),
                    joinedload(Property.type),
                    joinedload(Property.city),
                    joinedload(Property.area_rel),
                )
                .where(Property.id == uuid_obj)
            ).unique().scalar_one()
    except (ValueError, TypeError):
        # Not a UUID, try as int hash
        try:
            target_hash = int(property_id)
            # Search all properties to find matching hash
            all_props = db.execute(select(Property)).scalars().all()
            for p in all_props:
                if isinstance(p.id, uuid.UUID):
                    prop_hash = uuid_to_int_hash(p.id)
                    if prop_hash == target_hash:
                        # Reload with relationships
                        prop = db.execute(
        select(Property)
                            .options(
                                joinedload(Property.category),
                                joinedload(Property.type),
                                joinedload(Property.city),
                                joinedload(Property.area_rel),
                            )
                            .where(Property.id == p.id)
                        ).unique().scalar_one()
                        break
        except (ValueError, TypeError):
            pass
    
    if not prop:
        raise HTTPException(
            status_code=STATUS_NOT_FOUND,
            detail=ErrorMessages.PROPERTY_NOT_FOUND
        )
    
    # Build similarity filters with joins (include translations for multi-lang title/description)
    stmt = select(Property).options(
        joinedload(Property.category),
        joinedload(Property.type),
        joinedload(Property.city),
        joinedload(Property.area_rel),
        joinedload(Property.translations),
    )
    stmt = stmt.join(PropertyCategory, Property.category_id == PropertyCategory.id)
    stmt = stmt.join(City, Property.city_id == City.id)
    
    filters = []
    
    # Exclude the current property
    filters.append(Property.id != prop.id)
    
    # Same category/type - use relationships
    if prop.category_id:
        filters.append(Property.category_id == prop.category_id)
    
    # Same city - use relationship
    if prop.city_id:
        filters.append(Property.city_id == prop.city_id)
    
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
    
    # Similar area (±20%) - normalized model uses 'area' field
    area_value = getattr(prop, 'area', None) or getattr(prop, 'built_up_area', None)
    if area_value:
        area = float(area_value)
        min_area = area * (1 - price_tolerance)
        max_area = area * (1 + price_tolerance)
        filters.append(
            and_(
                Property.area.isnot(None),
                Property.area >= min_area,
                Property.area <= max_area,
            )
        )
    
    # Apply filters
    if filters:
        stmt = stmt.where(and_(*filters))
    
    # Order by relevance (same category first, then by price similarity, then by creation date)
    stmt = stmt.order_by(Property.created_at.desc()).limit(limit)
    
    # Execute query - use unique() to avoid duplicate rows from joins
    results = db.execute(stmt).unique().scalars().all()

    # Convert to extended format
    data = [
        PropertySearchResultExtended.from_orm_obj(p, lang=lang)
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
    property_id: str,  # FastAPI path params are always strings
    db: DBSessionDep,
    lang: Optional[str] = Query(None, description="Language code for title/description: en, ar, esp, fr"),
) -> PropertyDetail:
    """
    Get detailed information about a specific property.
    
    Args:
        property_id: The unique identifier of the property (int hash or UUID string)
        
    Returns:
        PropertyDetail with all property information
        
    Raises:
        HTTPException: 404 if property not found
    """
    # Try to get property - handle both UUID and int (hash) IDs
    # FastAPI path parameters are always strings, so we need to parse them
    prop = None
    import uuid
    from app.schemas.property import uuid_to_int_hash
    
    # Try to parse as UUID first
    try:
        uuid_obj = uuid.UUID(property_id)
        prop = db.get(Property, uuid_obj)
        if prop:
            # Reload with relationships
            prop = db.execute(
                select(Property)
                .options(
                    joinedload(Property.category),
                    joinedload(Property.type),
                    joinedload(Property.city),
                    joinedload(Property.area_rel),
                    joinedload(Property.property_status),
                    joinedload(Property.translations),
                    joinedload(Property.features).joinedload(PropertyFeature.feature),
                )
                .where(Property.id == uuid_obj)
            ).unique().scalar_one()
    except (ValueError, TypeError):
        # Not a UUID, try as int hash
        try:
            # If int, search all properties and match by hash
            # Note: This is inefficient for large datasets. Consider adding a hash->UUID mapping table.
            
            # Convert property_id to int for comparison
            target_hash = int(property_id)
            # Query all properties - first without relationships to speed up search
            print(f"[DEBUG] Looking up property with hash: {target_hash} (type: {type(target_hash)})")
            logger.info(f"Looking up property with hash: {target_hash}")
            all_props = db.execute(select(Property)).scalars().all()
            print(f"[DEBUG] Found {len(all_props)} properties in database")
            logger.info(f"Found {len(all_props)} properties in database")
            
            if not all_props:
                logger.warning(f"No properties found in database when searching for hash {target_hash}")
            else:
                # Search through properties to find matching hash
                found_uuid = None
                checked = 0
                sample_hashes = []
                
                for p in all_props:
                    if isinstance(p.id, uuid.UUID):
                        # Calculate hash the same way as in PropertySearchResultExtended
                        prop_hash = uuid_to_int_hash(p.id)
                        checked += 1
                        
                        # Collect first 5 hashes for debugging
                        if checked <= 5:
                            sample_hashes.append(f"UUID {p.id} -> hash {prop_hash}")
                        
                        if prop_hash == target_hash:
                            found_uuid = p.id
                            print(f"[DEBUG] Found matching property! UUID: {p.id}, hash: {prop_hash}")
                            logger.info(f"Found matching property! UUID: {p.id}, hash: {prop_hash}")
                            break
                
                if not found_uuid:
                    warning_msg = (
                        f"Property with hash {target_hash} not found after checking {checked} properties. "
                        f"Sample hashes: {', '.join(sample_hashes)}"
                    )
                    print(f"[DEBUG] {warning_msg}")
                    logger.warning(warning_msg)
                else:
                    # If found, reload with relationships
                    prop = db.execute(
                        select(Property)
                        .options(
                            joinedload(Property.category),
                            joinedload(Property.type),
                            joinedload(Property.city),
                            joinedload(Property.area_rel),
                            joinedload(Property.property_status),
                            joinedload(Property.translations),
                            joinedload(Property.features).joinedload(PropertyFeature.feature),
                        )
                        .where(Property.id == found_uuid)
                    ).unique().scalar_one()
                    logger.info(f"Successfully loaded property {found_uuid} with relationships")
        except (ValueError, TypeError) as e:
            # Could not parse as int either
            print(f"[DEBUG] Could not parse property_id '{property_id}' as UUID or int: {e}")
            logger.error(f"Could not parse property_id '{property_id}' as UUID or int: {e}")
        except Exception as e:
            # Log the error for debugging
            print(f"[DEBUG] Error in property lookup: {e}")
            logger.error(f"Error in property lookup for hash {target_hash}: {e}", exc_info=True)
            # Don't re-raise, let it fall through to 404
    
    if not prop:
        raise HTTPException(
            status_code=STATUS_NOT_FOUND,
            detail=ErrorMessages.PROPERTY_NOT_FOUND
        )
    return PropertyDetail.from_orm_obj(prop, lang=lang)

