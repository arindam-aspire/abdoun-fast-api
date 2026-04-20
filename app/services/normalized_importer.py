"""Import CSV into normalized property tables (categories, types, cities, areas, features, translations, media)."""
from __future__ import annotations
import json
import re
from typing import Any, Optional
from uuid import UUID, uuid4

import pandas as pd
from sqlalchemy import bindparam, select, update
from sqlalchemy.orm import Session

from app.models.property_normalized import (
    PropertyNormalized,
    PropertyCategory,
    PropertyType,
    City,
    Area,
    Feature,
    PropertyStatus,
    PropertyFeature,
    PropertyTranslation,
    PropertyMedia,
)
from app.services.translation_service import get_or_create_translation
from app.schemas.property import (
    FEATURE_VALUE_KEYS,
    META_FEATURE_NAMES,
    FEATURE_VALUE_LIKE_NAMES,
)
from app.services.csv_importer import (
    _parse_price,
    _parse_area,
    _parse_int,
    logger,
)
from app.utils.constants import ImportDefaults
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.logger import get_logger

# Re-define helper functions that might not be exported
def _normalize_string(value: Any) -> str | None:
    """Normalize string value."""
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text if text and text.lower() not in ("nan", "none", "") else None


def _normalize_location_name(value: Any) -> str | None:
    """Normalize location name."""
    return _normalize_string(value)
from sqlalchemy import func


def parse_more_features_to_json(more_features_list: list[str] | None) -> dict | None:
    """
    Parse pipe-separated more_features list into key-value JSON object.
    
    Example:
        Input: ['Finishing', 'Deluxe', 'Windows', 'Double Glazed', 'Heating System', 'Central']
        Output: {'Finishing': 'Deluxe', 'Windows': 'Double Glazed', 'Heating System': 'Central'}
    
    Args:
        more_features_list: List of strings from pipe-separated CSV column
        
    Returns:
        Dictionary with key-value pairs, or None if input is empty/invalid
    """
    if not more_features_list:
        return None
    
    # Filter out empty strings
    features = [f.strip() for f in more_features_list if f and f.strip()]
    
    if not features:
        return None
    
    # If odd number of items, ignore the last one (no matching value)
    if len(features) % 2 != 0:
        features = features[:-1]
    
    # Convert to key-value pairs
    result = {}
    for i in range(0, len(features), 2):
        key = features[i]
        value = features[i + 1] if i + 1 < len(features) else None
        if key and value:
            result[key] = value
    
    return result if result else None


def _parse_rent_commission(value: Any) -> float | None:
    """Parse rent_commission from CSV (e.g. '5.00 %' -> 5.0)."""
    if value is None or pd.isna(value):
        return None
    s = str(value).strip().replace("%", "").replace(",", ".").strip()
    if not s or s.lower() in ("nan", "none", "undefined"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _filter_features_to_amenities(
    features_list: list[str],
    more_features_json: dict | None,
) -> list[str]:
    """
    Keep only real amenities from CSV 'features' column.
    Exclude: value-slot keys (Finishing, Windows, ...), meta names (Floor Type, Garage, ...),
    value-like names (Standard, Deluxe, ...), and any key/value from more_features.
    """
    excluded = set(FEATURE_VALUE_KEYS) | set(META_FEATURE_NAMES) | set(FEATURE_VALUE_LIKE_NAMES)
    if more_features_json:
        for k, v in more_features_json.items():
            if k:
                excluded.add(k.strip())
            if v and isinstance(v, str):
                excluded.add(v.strip())
    return [
        f for f in features_list
        if f and f.strip() and f.strip() not in excluded
    ]


def _slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text


def get_or_create_category(
    db: Session,
    category_name: str,
    cache_by_slug: dict[str, PropertyCategory] | None = None,
) -> PropertyCategory:
    """Get or create a property category."""
    if not category_name:
        category_name = ImportDefaults.CATEGORY_OTHER
    
    slug = _slugify(category_name)
    
    if cache_by_slug is not None and slug in cache_by_slug:
        return cache_by_slug[slug]

    # Try to find existing category
    category = db.execute(
        select(PropertyCategory).where(PropertyCategory.slug == slug)
    ).scalar_one_or_none()
    
    if category:
        if cache_by_slug is not None:
            cache_by_slug[slug] = category
        return category
    
    # Create new category
    category = PropertyCategory(name=category_name, slug=slug, is_active=True)
    db.add(category)
    db.flush()
    if cache_by_slug is not None:
        cache_by_slug[slug] = category
    return category


def get_or_create_type(
    db: Session,
    type_name: str,
    category_id: int,
    cache_by_slug_and_category: dict[tuple[str, int], PropertyType] | None = None,
) -> PropertyType:
    """Get or create a property type."""
    if not type_name:
        type_name = ImportDefaults.TYPE_OTHER
    
    slug = _slugify(type_name)
    
    cache_key = (slug, category_id)
    if cache_by_slug_and_category is not None and cache_key in cache_by_slug_and_category:
        return cache_by_slug_and_category[cache_key]

    # Try to find existing type
    prop_type = db.execute(
        select(PropertyType).where(
            PropertyType.slug == slug,
            PropertyType.category_id == category_id
        )
    ).scalar_one_or_none()
    
    if prop_type:
        if cache_by_slug_and_category is not None:
            cache_by_slug_and_category[cache_key] = prop_type
        return prop_type
    
    # Create new type
    prop_type = PropertyType(
        name=type_name,
        slug=slug,
        category_id=category_id,
        is_active=True
    )
    db.add(prop_type)
    db.flush()
    if cache_by_slug_and_category is not None:
        cache_by_slug_and_category[cache_key] = prop_type
    return prop_type


def get_or_create_city(
    db: Session,
    city_name: str,
    cache_by_lower_name: dict[str, City] | None = None,
) -> City:
    """Get or create a city."""
    if not city_name:
        city_name = ImportDefaults.LOCATION_UNKNOWN
    
    city_name = city_name.strip()
    city_key = city_name.lower()
    if cache_by_lower_name is not None and city_key in cache_by_lower_name:
        return cache_by_lower_name[city_key]
    
    # Try to find existing city
    city = db.execute(
        select(City).where(func.lower(City.name) == func.lower(city_name))
    ).scalar_one_or_none()
    
    if city:
        if cache_by_lower_name is not None:
            cache_by_lower_name[city_key] = city
        return city
    
    # Create new city
    city = City(name=city_name, is_active=True)
    db.add(city)
    db.flush()
    if cache_by_lower_name is not None:
        cache_by_lower_name[city_key] = city
    return city


def get_or_create_area(
    db: Session,
    area_name: str,
    city_id: int,
    cache_by_name_and_city: dict[tuple[str, int], Area] | None = None,
) -> Area:
    """Get or create an area."""
    if not area_name:
        area_name = ImportDefaults.LOCATION_UNKNOWN
    
    area_name = area_name.strip()
    area_key = (area_name.lower(), city_id)
    if cache_by_name_and_city is not None and area_key in cache_by_name_and_city:
        return cache_by_name_and_city[area_key]
    
    # Try to find existing area
    area = db.execute(
        select(Area).where(
            func.lower(Area.name) == func.lower(area_name),
            Area.city_id == city_id
        )
    ).scalar_one_or_none()
    
    if area:
        if cache_by_name_and_city is not None:
            cache_by_name_and_city[area_key] = area
        return area
    
    # Create new area
    area = Area(name=area_name, city_id=city_id, is_active=True)
    db.add(area)
    db.flush()
    if cache_by_name_and_city is not None:
        cache_by_name_and_city[area_key] = area
    return area


def get_or_create_status(
    db: Session,
    status_name: str,
    cache_by_slug: dict[str, PropertyStatus] | None = None,
) -> PropertyStatus:
    """Get or create a property status."""
    if not status_name:
        status_name = ImportDefaults.STATUS_PENDING
    
    slug = _slugify(status_name)
    
    if cache_by_slug is not None and slug in cache_by_slug:
        return cache_by_slug[slug]

    # Try to find existing status
    status = db.execute(
        select(PropertyStatus).where(PropertyStatus.slug == slug)
    ).scalar_one_or_none()
    
    if status:
        if cache_by_slug is not None:
            cache_by_slug[slug] = status
        return status
    
    # Create new status
    status = PropertyStatus(name=status_name, slug=slug, is_active=True)
    db.add(status)
    db.flush()
    if cache_by_slug is not None:
        cache_by_slug[slug] = status
    return status


def get_or_create_feature(
    db: Session,
    feature_name: str,
    cache_by_slug: dict[str, Feature] | None = None,
) -> Optional[Feature]:
    """Get or create a feature."""
    if not feature_name:
        return None
    
    slug = _slugify(feature_name)
    
    if cache_by_slug is not None and slug in cache_by_slug:
        return cache_by_slug[slug]

    # Try to find existing feature
    feature = db.execute(
        select(Feature).where(Feature.slug == slug)
    ).scalar_one_or_none()
    
    if feature:
        if cache_by_slug is not None:
            cache_by_slug[slug] = feature
        return feature
    
    # Create new feature
    feature = Feature(name=feature_name, slug=slug, is_active=True)
    db.add(feature)
    db.flush()
    if cache_by_slug is not None:
        cache_by_slug[slug] = feature
    return feature


def _preload_lookup_caches(
    db: Session,
    category_cache: dict[str, PropertyCategory],
    type_cache: dict[tuple[str, int], PropertyType],
    city_cache: dict[str, City],
    area_cache: dict[tuple[str, int], Area],
    status_cache: dict[str, PropertyStatus],
    feature_cache: dict[str, Feature],
) -> None:
    """Preload lookup tables into memory to avoid first-hit query bursts."""
    for obj in db.execute(select(PropertyCategory)).scalars().all():
        if obj.slug:
            category_cache[obj.slug] = obj
    for obj in db.execute(select(PropertyType)).scalars().all():
        if obj.slug and obj.category_id is not None:
            type_cache[(obj.slug, obj.category_id)] = obj
    for obj in db.execute(select(City)).scalars().all():
        if obj.name:
            city_cache[obj.name.strip().lower()] = obj
    for obj in db.execute(select(Area)).scalars().all():
        if obj.name and obj.city_id is not None:
            area_cache[(obj.name.strip().lower(), obj.city_id)] = obj
    for obj in db.execute(select(PropertyStatus)).scalars().all():
        if obj.slug:
            status_cache[obj.slug] = obj
    for obj in db.execute(select(Feature)).scalars().all():
        if obj.slug:
            feature_cache[obj.slug] = obj


def parse_location(location_str: str) -> tuple[str, str]:
    """Parse location string like 'Dabouq - Amman' into (area, city)."""
    if not location_str:
        return (ImportDefaults.LOCATION_UNKNOWN, ImportDefaults.LOCATION_UNKNOWN)
    parts = location_str.split(" - ")
    if len(parts) >= 2:
        area = parts[0].strip()
        city = parts[-1].strip()
    elif len(parts) == 1:
        area = parts[0].strip()
        city = ImportDefaults.DEFAULT_CITY
    else:
        area = ImportDefaults.LOCATION_UNKNOWN
        city = ImportDefaults.LOCATION_UNKNOWN
    return (area, city)


def parse_category_type(category_str: str) -> tuple[str, str]:
    """Parse category string to extract category and type."""
    if not category_str:
        return ("Other", "Other")
    
    category_lower = category_str.lower()
    
    # Determine category
    if "apartment" in category_lower:
        category = "Residential"
        prop_type = "Apartment"
    elif "villa" in category_lower or "house" in category_lower:
        category = "Residential"
        prop_type = "Villa" if "villa" in category_lower else "House"
    elif "building" in category_lower:
        category = "Residential"
        prop_type = "Building"
    elif "farm" in category_lower:
        category = "Residential"
        prop_type = "Farm"
    elif "office" in category_lower:
        category = "Commercial"
        prop_type = "Office"
    elif "showroom" in category_lower:
        category = "Commercial"
        prop_type = "Showroom"
    elif "warehouse" in category_lower:
        category = "Commercial"
        prop_type = "Warehouse"
    elif "business" in category_lower:
        category = "Commercial"
        prop_type = "Business"
    elif "land" in category_lower:
        category = "Land"
        prop_type = "Land"
    else:
        category = "Residential"
        prop_type = category_str
    
    return (category, prop_type)


def determine_property_status(row: pd.Series) -> str:
    """Determine property status from CSV row."""
    status = _normalize_string(row.get("status"))
    if status and status.lower() == ImportDefaults.STATUS_OK_LOWER:
        return ImportDefaults.STATUS_VERIFIED
    return ImportDefaults.STATUS_PENDING


def create_property_normalized_from_row(
    db: Session,
    row: pd.Series,
    url: str,
    title: str,
    lat_f: float | None,
    lng_f: float | None,
    selling_amount: float | None,
    selling_currency: str | None,
    rent_amount: float | None,
    rent_currency: str | None,
    images: list[str],
    more_features_json: dict | None = None,
    lookup_caches: dict[str, dict] | None = None,
) -> PropertyNormalized:
    """Create a PropertyNormalized object from a CSV row."""
    
    # Parse category and type
    category_str = _normalize_string(row.get("category")) or ImportDefaults.CATEGORY_OTHER
    category_name, type_name = parse_category_type(category_str)
    
    category_cache = lookup_caches.get("category") if lookup_caches else None
    type_cache = lookup_caches.get("type") if lookup_caches else None
    city_cache = lookup_caches.get("city") if lookup_caches else None
    area_cache = lookup_caches.get("area") if lookup_caches else None
    status_cache = lookup_caches.get("status") if lookup_caches else None

    # Get or create category and type
    category = get_or_create_category(db, category_name, cache_by_slug=category_cache)
    prop_type = get_or_create_type(
        db,
        type_name,
        category.id,
        cache_by_slug_and_category=type_cache,
    )
    
    # Parse location
    location_str = _normalize_location_name(row.get("location"))
    area_name, city_name = parse_location(location_str)
    
    # Get or create city and area
    city = get_or_create_city(db, city_name, cache_by_lower_name=city_cache)
    area = get_or_create_area(db, area_name, city.id, cache_by_name_and_city=area_cache)
    
    # Get or create status
    status_name = determine_property_status(row)
    status = get_or_create_status(db, status_name, cache_by_slug=status_cache)
    
    # Determine primary price
    if selling_amount:
        primary_price = selling_amount
    elif rent_amount:
        primary_price = rent_amount
    else:
        primary_price = 0.0
    
    # Parse other fields
    area_value = _parse_area(row.get("built_up_area")) or _parse_area(row.get("area_sqm"))
    bedrooms = _parse_int(row.get("bedrooms"))
    bathrooms = _parse_int(row.get("bathrooms"))
    rooms = _parse_int(row.get("rooms"))
    
    furniture_status = _normalize_string(row.get("furniture"))
    parking = _normalize_string(row.get("garage")) is not None

    # Reference number from CSV property_id (e.g. "01002") for display/SEO
    reference_number = _normalize_string(row.get("property_id"))

    # Pricing extras from CSV: rent_commission ("5.00 %"), contract_duration ("Undefined"), payment_method ("Annual")
    rent_commission_percent = _parse_rent_commission(row.get("rent_commission"))
    contract_duration_raw = _normalize_string(row.get("contract_duration"))
    contract_duration = contract_duration_raw if contract_duration_raw and contract_duration_raw.lower() != "undefined" else None
    payment_method_raw = _normalize_string(row.get("payment_method"))
    payment_method = payment_method_raw.strip().lower() if payment_method_raw else None

    # Store images as JSON string
    images_json = json.dumps(images) if images else "[]"
    virtual_tour_url = _normalize_string(row.get("virtual_tour_url"))
    
    # Create property
    prop = PropertyNormalized(
        category_id=category.id,
        type_id=prop_type.id,
        property_status_id=status.id,
        city_id=city.id,
        location_id=area.id,
        url=url if url else None,
        title=title,
        description=_normalize_string(row.get("description")),
        is_verified=(status_name == ImportDefaults.STATUS_VERIFIED),
        latitude=lat_f,
        longitude=lng_f,
        location_name=location_str,  # Keep for backward compatibility
        price=primary_price,
        currency=selling_currency or rent_currency or "JOD",
        selling_price_amount=selling_amount,
        selling_price_currency=selling_currency,
        rent_price_amount=rent_amount,
        rent_price_currency=rent_currency,
        area=area_value,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        rooms=rooms,
        furniture_status=furniture_status,
        parking=parking,
        images=images_json,
        virtual_tour_url=virtual_tour_url,
        more_features=more_features_json,
        reference_number=reference_number,
        rent_commission_percent=rent_commission_percent,
        contract_duration=contract_duration,
        payment_method=payment_method,
    )

    if prop.id is None:
        prop.id = uuid4()
    from app.schemas.property import uuid_to_int_hash
    prop.property_hash = uuid_to_int_hash(prop.id)

    # Set location geometry if coordinates available
    if lat_f is not None and lng_f is not None:
        prop.location = func.ST_SetSRID(
            func.ST_MakePoint(lng_f, lat_f),
            4326,
        )
    
    return prop


def add_property_media_from_images(
    db: Session,
    property_id: UUID,
    images: list[str] | None,
) -> None:
    """Normalize image URLs into property_media rows (media_type='image')."""
    if not images:
        return

    seen_urls: set[str] = set()
    media_rows: list[PropertyMedia] = []
    for idx, raw_url in enumerate(images, start=1):
        url = _normalize_string(raw_url)
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        media_rows.append(
            PropertyMedia(
                property_id=property_id,
                media_type="image",
                url=url,
                thumb_url=url,
                is_primary=(len(media_rows) == 0),
                display_order=idx,
                caption=None,
            )
        )

    if media_rows:
        db.add_all(media_rows)


def add_property_features(
    db: Session,
    property_id: UUID,
    features_list: list[str],
    feature_cache: dict[str, Feature] | None = None,
):
    """Add features to a property."""
    # Deduplicate features list first (case-insensitive)
    seen_features = set()
    unique_features = []
    for feature_name in features_list:
        if not feature_name or not feature_name.strip():
            continue
        normalized_name = feature_name.strip().lower()
        if normalized_name not in seen_features:
            seen_features.add(normalized_name)
            unique_features.append(feature_name.strip())

    if not unique_features:
        return

    # Get all existing relationships for this property in one query
    existing_relationships = db.execute(
        select(PropertyFeature.feature_id).where(
            PropertyFeature.property_id == property_id
        )
    ).scalars().all()
    existing_feature_ids = set(existing_relationships)

    # Get or create features and collect new ones to add
    new_prop_features = []
    for feature_name in unique_features:
        feature = get_or_create_feature(db, feature_name, cache_by_slug=feature_cache)
        if feature and feature.id not in existing_feature_ids:
            new_prop_features.append(
                PropertyFeature(
                    property_id=property_id,
                    feature_id=feature.id
                )
            )
            existing_feature_ids.add(feature.id)  # Prevent duplicates in same batch

    # Bulk add new features
    if new_prop_features:
        db.add_all(new_prop_features)


# CSV column -> Feature name for "meta" fields stored as Feature + PropertyFeature.value
META_FEATURE_COLUMNS = [
    ("type", "Floor Type"),           # Upper Floor, Ground, Semi Ground Floor, Detached, etc.
    ("floor", "Floor"),               # 1.0, -1.0, 0.0
    ("building_status", "Building Status"),  # Used, New
    ("garage", "Garage"),             # Closed, Open
    ("terrace_area", "Terrace Area"), # 50 Sqm, 170 Sqm, etc.
    ("garden_area", "Garden Area"),   # 50 Sqm, etc.
    ("master_bedrooms", "Master Bedrooms"),  # 1.0, 2.0
    ("kitchens", "Kitchens"),         # 1.0
    ("furniture", "Furniture"),       # Furnished, Unfurnished (also in column; feature for consistency)
]


def _format_meta_value(raw: Any, column: str) -> str | None:
    """Format a CSV cell value for storage in PropertyFeature.value."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none"):
        return None
    # Normalize float-looking integers for floor, master_bedrooms, kitchens
    if column in ("floor", "master_bedrooms", "kitchens"):
        try:
            f = float(s)
            if f == int(f):
                return str(int(f))
            return s
        except ValueError:
            return s
    return s


def _meta_feature_value(row: pd.Series, csv_col: str) -> Optional[str]:
    raw = row.get(csv_col)
    if csv_col in ("terrace_area", "garden_area"):
        num = _parse_area(raw)
        if num is None:
            return None
        return str(int(num)) if num == int(num) else str(num)
    return _format_meta_value(raw, csv_col)


def _upsert_property_feature_value(db: Session, property_id: UUID, feature_id: int, value_str: str) -> None:
    bind = db.get_bind()
    dialect = bind.dialect.name
    if dialect in ("postgresql", "sqlite"):
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as dialect_insert
        else:
            from sqlalchemy.dialects.sqlite import insert as dialect_insert

        stmt = dialect_insert(PropertyFeature).values(
            property_id=property_id,
            feature_id=feature_id,
            value=value_str,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[PropertyFeature.property_id, PropertyFeature.feature_id],
            set_={
                "value": stmt.excluded.value,
                "updated_at": func.now(),
            },
        )
        db.execute(stmt)
        return

    existing = db.execute(
        select(PropertyFeature).where(
            PropertyFeature.property_id == property_id,
            PropertyFeature.feature_id == feature_id,
        )
    ).scalar_one_or_none()
    if existing:
        existing.value = value_str
    else:
        db.add(PropertyFeature(property_id=property_id, feature_id=feature_id, value=value_str))


def add_property_meta_features(
    db: Session,
    property_id: UUID,
    row: pd.Series,
    feature_cache: dict[str, Feature] | None = None,
) -> None:
    """
    Add meta fields from CSV as features with values (when not already table columns).
    Uses META_FEATURE_COLUMNS: (csv_column, feature_name). Value is stored in PropertyFeature.value.
    """
    for csv_col, feature_name in META_FEATURE_COLUMNS:
        value_str = _meta_feature_value(row, csv_col)
        if not value_str:
            continue
        feature = get_or_create_feature(db, feature_name, cache_by_slug=feature_cache)
        if not feature:
            continue
        _upsert_property_feature_value(db, property_id, feature.id, value_str)


def import_properties_normalized_from_dataframe(
    db: Session,
    df: pd.DataFrame,
    geocode_missing: bool = False,
    skip_duplicates: bool = True,
) -> int:
    """
    Import properties from DataFrame into normalized database structure.
    
    Args:
        db: Database session
        df: DataFrame containing property data
        geocode_missing: If True, geocode locations that don't have coordinates
        skip_duplicates: If True, skip properties that already exist (by URL)
    
    Returns:
        Number of properties imported
    """
    # Import parsing functions from csv_importer
    # These are internal functions, so we need to import the module
    import app.services.csv_importer as csv_importer
    
    imported_count = 0
    skipped_duplicates = 0
    pending_virtual_tour_updates: dict[str, str] = {}
    category_cache: dict[str, PropertyCategory] = {}
    type_cache: dict[tuple[str, int], PropertyType] = {}
    city_cache: dict[str, City] = {}
    area_cache: dict[tuple[str, int], Area] = {}
    status_cache: dict[str, PropertyStatus] = {}
    feature_cache: dict[str, Feature] = {}
    lookup_caches: dict[str, dict] = {
        "category": category_cache,
        "type": type_cache,
        "city": city_cache,
        "area": area_cache,
        "status": status_cache,
    }
    prev_expire_on_commit = db.expire_on_commit
    db.expire_on_commit = False
    try:
        _preload_lookup_caches(
            db,
            category_cache=category_cache,
            type_cache=type_cache,
            city_cache=city_cache,
            area_cache=area_cache,
            status_cache=status_cache,
            feature_cache=feature_cache,
        )

        # Import geocoding service only if needed
        geocoding_service = csv_importer._get_geocoding_service(geocode_missing) if geocode_missing else None
        
        # Load existing properties by URL if skipping duplicates
        existing_urls = set()
        existing_virtual_tour_by_url: dict[str, str | None] = {}
        if skip_duplicates:
            existing_rows = db.execute(
                select(PropertyNormalized.url, PropertyNormalized.virtual_tour_url).where(
                    PropertyNormalized.url.isnot(None)
                )
            ).all()
            existing_virtual_tour_by_url = {url: virtual_tour for url, virtual_tour in existing_rows if url}
            existing_urls = set(existing_virtual_tour_by_url.keys())
        
        for _, row in df.iterrows():
            # Parse row data (reuse existing parsing logic)
            (selling_amount, selling_currency, rent_amount, rent_currency,
             images, features, more_features, lat_f, lng_f, title, url, _) = csv_importer._parse_row_data(
                row, geocode_missing, geocoding_service
            )
            
            # Skip if duplicate
            if skip_duplicates and url and url in existing_urls:
                virtual_tour_url = _normalize_string(row.get("virtual_tour_url"))
                if (
                    virtual_tour_url
                    and not _normalize_string(existing_virtual_tour_by_url.get(url))
                ):
                    pending_virtual_tour_updates[url] = virtual_tour_url
                    existing_virtual_tour_by_url[url] = virtual_tour_url
                skipped_duplicates += 1
                continue
            
            try:
                # CSV 'features' = amenities only; 'more_features' = value slots (Finishing|Deluxe|...).
                all_features = list(features) if features else []
                more_features_json = parse_more_features_to_json(more_features)
                # Only add real amenities to PropertyFeature; value keys/values stay in more_features JSON.
                amenities_only = _filter_features_to_amenities(all_features, more_features_json)

                # Create property
                prop = create_property_normalized_from_row(
                    db=db,
                    row=row,
                    url=url,
                    title=title,
                    lat_f=lat_f,
                    lng_f=lng_f,
                    selling_amount=selling_amount,
                    selling_currency=selling_currency,
                    rent_amount=rent_amount,
                    rent_currency=rent_currency,
                    images=images,
                    more_features_json=more_features_json,
                    lookup_caches=lookup_caches,
                )
                
                db.add(prop)
                db.flush()  # Flush to get generated DB fields

                # Add English translation (title, description) to property_translations
                get_or_create_translation(
                    db,
                    property_id=prop.id,
                    language_code="en",
                    title=title,
                    description=_normalize_string(row.get("description")),
                    address=_normalize_location_name(row.get("location")),
                )

                # Add only amenities (value slots come from more_features JSON)
                if amenities_only:
                    add_property_features(db, prop.id, amenities_only, feature_cache=feature_cache)

                # Add meta fields as features with values (floor type, floor, building_status, garage, terrace_area, garden_area, master_bedrooms, kitchens, furniture)
                add_property_meta_features(db, prop.id, row, feature_cache=feature_cache)

                # Keep normalized media table in sync for new imports.
                add_property_media_from_images(db, prop.id, images)

                db.commit()
                imported_count += 1
                
                if url:
                    existing_urls.add(url)
                    
            except Exception as e:
                db.rollback()
                logger.error(
                    format_log_message(
                        LogMessages.Property.IMPORT_PROPERTY_ERROR,
                        url=url or "",
                        error=e,
                    )
                )
                skipped_duplicates += 1
                continue

        if pending_virtual_tour_updates:
            bulk_stmt = (
                update(PropertyNormalized)
                .where(PropertyNormalized.url == bindparam("target_url"))
                .where(PropertyNormalized.virtual_tour_url.is_(None))
                .values(virtual_tour_url=bindparam("target_virtual_tour_url"))
            )
            db.execute(
                bulk_stmt,
                [
                    {
                        "target_url": update_url,
                        "target_virtual_tour_url": update_value,
                    }
                    for update_url, update_value in pending_virtual_tour_updates.items()
                ],
            )
            db.commit()
    finally:
        db.expire_on_commit = prev_expire_on_commit
    
    logger.info(
        format_log_message(
            LogMessages.Property.IMPORTED_SKIPPED,
            imported_count=imported_count,
            skipped_duplicates=skipped_duplicates,
        )
    )
    return imported_count
