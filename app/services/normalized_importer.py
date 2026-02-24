"""
CSV importer service for normalized property structure.
Handles mapping CSV data to normalized database tables.
"""
import json
import re
from typing import Any, Optional
from uuid import UUID

import pandas as pd
from sqlalchemy import select
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
)
from app.services.csv_importer import (
    _parse_price,
    _parse_area,
    _parse_int,
    logger,
)
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


def _slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text


def get_or_create_category(db: Session, category_name: str) -> PropertyCategory:
    """Get or create a property category."""
    if not category_name:
        category_name = "Other"
    
    slug = _slugify(category_name)
    
    # Try to find existing category
    category = db.execute(
        select(PropertyCategory).where(PropertyCategory.slug == slug)
    ).scalar_one_or_none()
    
    if category:
        return category
    
    # Create new category
    category = PropertyCategory(name=category_name, slug=slug, is_active=True)
    db.add(category)
    db.flush()
    return category


def get_or_create_type(db: Session, type_name: str, category_id: int) -> PropertyType:
    """Get or create a property type."""
    if not type_name:
        type_name = "Other"
    
    slug = _slugify(type_name)
    
    # Try to find existing type
    prop_type = db.execute(
        select(PropertyType).where(
            PropertyType.slug == slug,
            PropertyType.category_id == category_id
        )
    ).scalar_one_or_none()
    
    if prop_type:
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
    return prop_type


def get_or_create_city(db: Session, city_name: str) -> City:
    """Get or create a city."""
    if not city_name:
        city_name = "Unknown"
    
    city_name = city_name.strip()
    
    # Try to find existing city
    city = db.execute(
        select(City).where(func.lower(City.name) == func.lower(city_name))
    ).scalar_one_or_none()
    
    if city:
        return city
    
    # Create new city
    city = City(name=city_name, is_active=True)
    db.add(city)
    db.flush()
    return city


def get_or_create_area(db: Session, area_name: str, city_id: int) -> Area:
    """Get or create an area."""
    if not area_name:
        area_name = "Unknown"
    
    area_name = area_name.strip()
    
    # Try to find existing area
    area = db.execute(
        select(Area).where(
            func.lower(Area.name) == func.lower(area_name),
            Area.city_id == city_id
        )
    ).scalar_one_or_none()
    
    if area:
        return area
    
    # Create new area
    area = Area(name=area_name, city_id=city_id, is_active=True)
    db.add(area)
    db.flush()
    return area


def get_or_create_status(db: Session, status_name: str) -> PropertyStatus:
    """Get or create a property status."""
    if not status_name:
        status_name = "pending"
    
    slug = _slugify(status_name)
    
    # Try to find existing status
    status = db.execute(
        select(PropertyStatus).where(PropertyStatus.slug == slug)
    ).scalar_one_or_none()
    
    if status:
        return status
    
    # Create new status
    status = PropertyStatus(name=status_name, slug=slug, is_active=True)
    db.add(status)
    db.flush()
    return status


def get_or_create_feature(db: Session, feature_name: str) -> Feature:
    """Get or create a feature."""
    if not feature_name:
        return None
    
    slug = _slugify(feature_name)
    
    # Try to find existing feature
    feature = db.execute(
        select(Feature).where(Feature.slug == slug)
    ).scalar_one_or_none()
    
    if feature:
        return feature
    
    # Create new feature
    feature = Feature(name=feature_name, slug=slug, is_active=True)
    db.add(feature)
    db.flush()
    return feature


def parse_location(location_str: str) -> tuple[str, str]:
    """Parse location string like 'Dabouq - Amman' into (area, city)."""
    if not location_str:
        return ("Unknown", "Unknown")
    
    parts = location_str.split(" - ")
    if len(parts) >= 2:
        area = parts[0].strip()
        city = parts[-1].strip()
    elif len(parts) == 1:
        area = parts[0].strip()
        city = "Amman"  # Default city
    else:
        area = "Unknown"
        city = "Unknown"
    
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
    if status and status.lower() == "ok":
        return "verified"
    return "pending"


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
    features_list: list[str],
    more_features_json: dict | None = None,
) -> PropertyNormalized:
    """Create a PropertyNormalized object from a CSV row."""
    
    # Parse category and type
    category_str = _normalize_string(row.get("category")) or "Other"
    category_name, type_name = parse_category_type(category_str)
    
    # Get or create category and type
    category = get_or_create_category(db, category_name)
    prop_type = get_or_create_type(db, type_name, category.id)
    
    # Parse location
    location_str = _normalize_location_name(row.get("location"))
    area_name, city_name = parse_location(location_str)
    
    # Get or create city and area
    city = get_or_create_city(db, city_name)
    area = get_or_create_area(db, area_name, city.id)
    
    # Get or create status
    status_name = determine_property_status(row)
    status = get_or_create_status(db, status_name)
    
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
    
    # Store images as JSON string
    images_json = json.dumps(images) if images else "[]"
    
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
        is_verified=(status_name == "verified"),
        latitude=lat_f,
        longitude=lng_f,
        location_name=location_str,  # Keep for backward compatibility
        price=primary_price,
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
    )
    
    # Set location geometry if coordinates available
    if lat_f is not None and lng_f is not None:
        prop.location = func.ST_SetSRID(
            func.ST_MakePoint(lng_f, lat_f),
            4326,
        )
    
    return prop


def add_property_features(
    db: Session,
    property_id: UUID,
    features_list: list[str],
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
        feature = get_or_create_feature(db, feature_name)
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
    
    # Import geocoding service only if needed
    geocoding_service = csv_importer._get_geocoding_service(geocode_missing) if geocode_missing else None
    
    # Load existing properties by URL if skipping duplicates
    existing_urls = set()
    if skip_duplicates:
        existing_props = db.execute(
            select(PropertyNormalized.url).where(PropertyNormalized.url.isnot(None))
        ).scalars().all()
        existing_urls = set(existing_props)
    
    for _, row in df.iterrows():
        # Parse row data (reuse existing parsing logic)
        (selling_amount, selling_currency, rent_amount, rent_currency,
         images, features, more_features, lat_f, lng_f, title, url) = csv_importer._parse_row_data(
            row, geocode_missing, geocoding_service
        )
        
        # Skip if duplicate
        if skip_duplicates and url and url in existing_urls:
            skipped_duplicates += 1
            continue
        
        try:
            # Combine features and more_features for PropertyFeature relationships
            all_features = []
            if features:
                all_features.extend(features)
            if more_features:
                all_features.extend(more_features)
            
            # Parse more_features into key-value JSON object
            more_features_json = parse_more_features_to_json(more_features)
            
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
                features_list=all_features,
                more_features_json=more_features_json,
            )
            
            db.add(prop)
            db.flush()  # Flush to get the property ID
            
            # Add features
            if all_features:
                add_property_features(db, prop.id, all_features)
            
            db.commit()
            imported_count += 1
            
            if url:
                existing_urls.add(url)
                
        except Exception as e:
            db.rollback()
            logger.error(f"Error importing property {url}: {e}")
            skipped_duplicates += 1
            continue
    
    logger.info(f"Imported {imported_count} properties, skipped {skipped_duplicates} duplicates")
    return imported_count

