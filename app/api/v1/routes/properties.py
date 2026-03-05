import uuid
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
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
    PropertySearchResultExtended,
    PropertySearchResponse,
    uuid_to_int_hash,
)
from app.utils.constants import ErrorMessages, Defaults
from app.utils.status_codes import STATUS_NOT_FOUND
from sqlalchemy.orm import joinedload

router = APIRouter()

DBSessionDep = Annotated[Session, Depends(get_db)]


def _append_status_filter(filters: list[Any], status_lower: Optional[str]) -> None:
    if status_lower == "buy":
        filters.append(Property.selling_price_amount.isnot(None))
    elif status_lower == "rent":
        filters.append(Property.rent_price_amount.isnot(None))


def _append_category_filter(filters: list[Any], category: Optional[str]) -> None:
    if not category:
        return

    category_lower = category.lower()
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


def _append_type_filter(filters: list[Any], type_slug: Optional[str]) -> None:
    if not type_slug:
        return

    type_lower = type_slug.lower().replace("-", " ")
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
    elif "office" in type_lower:
        filters.append(func.lower(PropertyType.name).contains("office"))
    elif "showroom" in type_lower:
        filters.append(func.lower(PropertyType.name).contains("showroom"))
    elif "warehouse" in type_lower:
        filters.append(func.lower(PropertyType.name).contains("warehouse"))
    elif "business" in type_lower:
        filters.append(func.lower(PropertyType.name).contains("business"))
    elif "land" in type_lower:
        filters.append(func.lower(PropertyType.name).contains("land"))
    else:
        filters.append(func.lower(PropertyType.name).contains(type_lower))


def _append_city_filter(filters: list[Any], city: Optional[str]) -> None:
    if not city:
        return

    city_lower = city.lower()
    filters.append(
        or_(
            func.lower(City.name).contains(city_lower),
            func.lower(Property.location_name).contains(city_lower),
        )
    )


def _append_locations_filter(filters: list[Any], locations: Optional[str]) -> None:
    if not locations:
        return

    location_list = [loc.strip().lower() for loc in locations.split(",") if loc.strip()]
    if not location_list:
        return

    location_filters = [
        or_(
            func.lower(Area.name).contains(loc),
            func.lower(Property.location_name).contains(loc),
        )
        for loc in location_list
    ]
    filters.append(or_(*location_filters))


def _append_exclusive_filter(filters: list[Any], exclusive: Optional[str]) -> None:
    if exclusive is None:
        return

    exclusive_bool = str(exclusive).lower() in ("true", "1", "yes")
    filters.append(Property.is_exclusive.is_(exclusive_bool))


def _append_budget_bound_filter(
    filters: list[Any],
    value_raw: Optional[str],
    status_lower: Optional[str],
    *,
    is_min: bool,
) -> None:
    if not value_raw:
        return

    try:
        value = float(value_raw)
    except (ValueError, TypeError):
        return

    if status_lower == "buy":
        condition = Property.selling_price_amount >= value if is_min else Property.selling_price_amount <= value
    elif status_lower == "rent":
        condition = Property.rent_price_amount >= value if is_min else Property.rent_price_amount <= value
    else:
        condition = or_(
            Property.selling_price_amount >= value if is_min else Property.selling_price_amount <= value,
            Property.rent_price_amount >= value if is_min else Property.rent_price_amount <= value,
        )
    filters.append(condition)


def _build_property_filters(
    *,
    status: Optional[str],
    category: Optional[str],
    type_slug: Optional[str],
    city: Optional[str],
    locations: Optional[str],
    exclusive: Optional[str],
    budget_min: Optional[str],
    budget_max: Optional[str],
    min_price: Optional[str],
    max_price: Optional[str],
) -> list[Any]:
    filters: list[Any] = []
    status_lower = status.lower() if status else None

    _append_status_filter(filters, status_lower)
    _append_category_filter(filters, category)
    _append_type_filter(filters, type_slug)
    _append_city_filter(filters, city)
    _append_locations_filter(filters, locations)
    _append_exclusive_filter(filters, exclusive)

    min_budget = budget_min or min_price
    max_budget = budget_max or max_price
    _append_budget_bound_filter(filters, min_budget, status_lower, is_min=True)
    _append_budget_bound_filter(filters, max_budget, status_lower, is_min=False)

    return filters


def _build_count_stmt(filters: list[Any], requires_joins: bool):
    count_stmt = select(func.count(Property.id))
    if requires_joins:
        count_stmt = count_stmt.join(PropertyCategory, Property.category_id == PropertyCategory.id)
        count_stmt = count_stmt.join(PropertyType, Property.type_id == PropertyType.id)
        count_stmt = count_stmt.join(City, Property.city_id == City.id)
        count_stmt = count_stmt.join(Area, Property.location_id == Area.id)
    if filters:
        count_stmt = count_stmt.where(and_(*filters))
    return count_stmt


class PropertySearchParams(BaseModel):
    status: Optional[str] = None
    category: Optional[str] = None
    type_slug: Optional[str] = None
    city: Optional[str] = None
    locations: Optional[str] = None
    budget_min: Optional[str] = None
    budget_max: Optional[str] = None
    min_price: Optional[str] = None
    max_price: Optional[str] = None
    exclusive: Optional[str] = None
    page: int = 1
    page_size: int = 12
    lang: Optional[str] = None


def _execute_property_search(db: Session, params: PropertySearchParams) -> PropertySearchResponse:
    stmt = select(Property).options(
        joinedload(Property.category),
        joinedload(Property.type),
        joinedload(Property.city),
        joinedload(Property.area_rel),
        joinedload(Property.property_status),
        joinedload(Property.translations),
    )

    stmt = stmt.join(PropertyCategory, Property.category_id == PropertyCategory.id)
    stmt = stmt.join(PropertyType, Property.type_id == PropertyType.id)
    stmt = stmt.join(City, Property.city_id == City.id)
    stmt = stmt.join(Area, Property.location_id == Area.id)

    filters = _build_property_filters(
        status=params.status,
        category=params.category,
        type_slug=params.type_slug,
        city=params.city,
        locations=params.locations,
        exclusive=params.exclusive,
        budget_min=params.budget_min,
        budget_max=params.budget_max,
        min_price=params.min_price,
        max_price=params.max_price,
    )

    if filters:
        stmt = stmt.where(and_(*filters))

    requires_joins = any((params.category, params.type_slug, params.city, params.locations))
    count_stmt = _build_count_stmt(filters, requires_joins)
    total = db.execute(count_stmt).scalar() or 0

    offset = (params.page - 1) * params.page_size
    stmt = stmt.order_by(Property.created_at.desc()).offset(offset).limit(params.page_size)
    results = db.execute(stmt).unique().scalars().all()

    data = [PropertySearchResultExtended.from_orm_obj(p, lang=params.lang) for p in results]
    return PropertySearchResponse(data=data, total=total, page=params.page, pageSize=params.page_size)


def get_property_search_params(
    status: Optional[str] = Query(None, description="Listing type: buy or rent"),
    category: Optional[str] = Query(None, description="One of: residential, commercial, land. On Hero, 'Land' is sent as lands."),
    type_slug: Optional[str] = Query(None, alias="type", description="Slugified property type (e.g., apartments, villas, residential-lands)"),
    city: Optional[str] = Query(None, description="City name, lowercase"),
    locations: Optional[str] = Query(None, description="Comma-separated area/neighborhood names, lowercase"),
    budget_min: Optional[str] = Query(None, alias="budgetMin", description="Minimum price in JD (numeric string)"),
    budget_max: Optional[str] = Query(None, alias="budgetMax", description="Maximum price in JD (numeric string)"),
    min_price: Optional[str] = Query(None, alias="minPrice", description="Alias for budgetMin (for hero search compatibility)"),
    max_price: Optional[str] = Query(None, alias="maxPrice", description="Alias for budgetMax (for hero search compatibility)"),
    exclusive: Optional[str] = Query(None, description="Filter by exclusive status (true/1 for exclusive only, false/0 for non-exclusive only)"),
    page: int = Query(1, ge=1, description="Page number, 1-based"),
    page_size: int = Query(12, alias="pageSize", ge=1, le=100, description="Items per page"),
    lang: Optional[str] = Query(None, description=Defaults.LANG_QUERY_DESCRIPTION),
) -> PropertySearchParams:
    return PropertySearchParams(
        status=status,
        category=category,
        type_slug=type_slug,
        city=city,
        locations=locations,
        budget_min=budget_min,
        budget_max=budget_max,
        min_price=min_price,
        max_price=max_price,
        exclusive=exclusive,
        page=page,
        page_size=page_size,
        lang=lang,
    )


def get_exclusive_property_search_params(
    status: Optional[str] = Query(None, description="Listing type: buy or rent"),
    category: Optional[str] = Query(None, description="One of: residential, commercial, land. On Hero, 'Land' is sent as lands."),
    type_slug: Optional[str] = Query(None, alias="type", description="Slugified property type (e.g., apartments, villas, residential-lands)"),
    city: Optional[str] = Query(None, description="City name, lowercase"),
    locations: Optional[str] = Query(None, description="Comma-separated area/neighborhood names, lowercase"),
    budget_min: Optional[str] = Query(None, alias="budgetMin", description="Minimum price in JD (numeric string)"),
    budget_max: Optional[str] = Query(None, alias="budgetMax", description="Maximum price in JD (numeric string)"),
    min_price: Optional[str] = Query(None, alias="minPrice", description="Alias for budgetMin (for hero search compatibility)"),
    max_price: Optional[str] = Query(None, alias="maxPrice", description="Alias for budgetMax (for hero search compatibility)"),
    page: int = Query(1, ge=1, description="Page number, 1-based"),
    page_size: int = Query(12, alias="pageSize", ge=1, le=100, description="Items per page"),
    lang: Optional[str] = Query(None, description=Defaults.LANG_QUERY_DESCRIPTION),
) -> PropertySearchParams:
    return PropertySearchParams(
        status=status,
        category=category,
        type_slug=type_slug,
        city=city,
        locations=locations,
        budget_min=budget_min,
        budget_max=budget_max,
        min_price=min_price,
        max_price=max_price,
        exclusive="true",
        page=page,
        page_size=page_size,
        lang=lang,
    )


def _load_property_with_options(db: Session, property_uuid: uuid.UUID, options: list[Any]) -> Optional[Property]:
    return db.execute(
        select(Property).options(*options).where(Property.id == property_uuid)
    ).unique().scalar_one_or_none()


def _find_property_uuid_by_hash(db: Session, target_hash: int) -> Optional[uuid.UUID]:
    property_ids = db.execute(select(Property.id)).scalars().all()
    for prop_id in property_ids:
        if isinstance(prop_id, uuid.UUID) and uuid_to_int_hash(prop_id) == target_hash:
            return prop_id
    return None


def _resolve_property_by_identifier(
    db: Session,
    property_id: str,
    options: list[Any],
) -> Optional[Property]:
    try:
        property_uuid = uuid.UUID(property_id)
        return _load_property_with_options(db, property_uuid, options)
    except (ValueError, TypeError):
        pass

    try:
        target_hash = int(property_id)
    except (ValueError, TypeError):
        return None

    property_uuid = _find_property_uuid_by_hash(db, target_hash)
    if not property_uuid:
        return None
    return _load_property_with_options(db, property_uuid, options)


@router.get("", response_model=PropertySearchResponse)
def list_properties(
    db: DBSessionDep,
    params: Annotated[PropertySearchParams, Depends(get_property_search_params)],
) -> PropertySearchResponse:
    """
    Search properties with optional filters and pagination.
    
    Matches the frontend search contract for Home Page and Search Results page.
    Supports both budgetMin/budgetMax and minPrice/maxPrice for compatibility.
    """
    return _execute_property_search(db, params)


@router.get("/exclusive", response_model=PropertySearchResponse)
def list_exclusive_properties(
    db: DBSessionDep,
    params: Annotated[PropertySearchParams, Depends(get_exclusive_property_search_params)],
) -> PropertySearchResponse:
    """
    List exclusive properties with optional filters and pagination.
    
    Same as regular property list endpoint but only returns properties where is_exclusive = True.
    Uses the same response format and supports all the same filters.
    """
    return _execute_property_search(db, params)


@router.get("/{property_id}/similar", response_model=PropertySearchResponse)
def get_similar_properties(
    property_id: str,  # FastAPI path params are always strings
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=50, description="Maximum number of similar properties to return"),
    lang: Optional[str] = Query(None, description=Defaults.LANG_QUERY_DESCRIPTION),
) -> PropertySearchResponse:
    """
    Get similar properties based on the selected property.
    """
    similar_options = [
        joinedload(Property.category),
        joinedload(Property.type),
        joinedload(Property.city),
        joinedload(Property.area_rel),
    ]
    prop = _resolve_property_by_identifier(db, property_id, similar_options)
    if not prop:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail=ErrorMessages.PROPERTY_NOT_FOUND)

    stmt = select(Property).options(
        joinedload(Property.category),
        joinedload(Property.type),
        joinedload(Property.city),
        joinedload(Property.area_rel),
        joinedload(Property.translations),
    )
    stmt = stmt.join(PropertyCategory, Property.category_id == PropertyCategory.id)
    stmt = stmt.join(City, Property.city_id == City.id)

    filters: list[Any] = [Property.id != prop.id]
    if prop.category_id:
        filters.append(Property.category_id == prop.category_id)
    if prop.city_id:
        filters.append(Property.city_id == prop.city_id)

    tolerance = 0.2
    if prop.selling_price_amount:
        price = float(prop.selling_price_amount)
        filters.append(
            and_(
                Property.selling_price_amount.isnot(None),
                Property.selling_price_amount >= price * (1 - tolerance),
                Property.selling_price_amount <= price * (1 + tolerance),
            )
        )
    elif prop.rent_price_amount:
        price = float(prop.rent_price_amount)
        filters.append(
            and_(
                Property.rent_price_amount.isnot(None),
                Property.rent_price_amount >= price * (1 - tolerance),
                Property.rent_price_amount <= price * (1 + tolerance),
            )
        )

    if prop.bedrooms:
        filters.append(or_(Property.bedrooms == prop.bedrooms, Property.bedrooms == prop.bedrooms - 1, Property.bedrooms == prop.bedrooms + 1))
    if prop.bathrooms:
        filters.append(or_(Property.bathrooms == prop.bathrooms, Property.bathrooms == prop.bathrooms - 1, Property.bathrooms == prop.bathrooms + 1))

    area_value = getattr(prop, "area", None) or getattr(prop, "built_up_area", None)
    if area_value:
        area = float(area_value)
        filters.append(and_(Property.area.isnot(None), Property.area >= area * (1 - tolerance), Property.area <= area * (1 + tolerance)))

    stmt = stmt.where(and_(*filters)).order_by(Property.created_at.desc()).limit(limit)
    results = db.execute(stmt).unique().scalars().all()
    data = [PropertySearchResultExtended.from_orm_obj(p, lang=lang) for p in results]
    return PropertySearchResponse(data=data, total=len(data), page=1, pageSize=len(data))


@router.get("/{property_id}", response_model=PropertyDetail)
def get_property(
    property_id: str,  # FastAPI path params are always strings
    db: DBSessionDep,
    lang: Optional[str] = Query(None, description=Defaults.LANG_QUERY_DESCRIPTION),
) -> PropertyDetail:
    """
    Get detailed information about a specific property.
    """
    detail_options = [
        joinedload(Property.category),
        joinedload(Property.type),
        joinedload(Property.city),
        joinedload(Property.area_rel),
        joinedload(Property.property_status),
        joinedload(Property.translations),
        joinedload(Property.features).joinedload(PropertyFeature.feature),
    ]
    prop = _resolve_property_by_identifier(db, property_id, detail_options)
    if not prop:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail=ErrorMessages.PROPERTY_NOT_FOUND)
    return PropertyDetail.from_orm_obj(prop, lang=lang)
