"""CSV property import: parse price/area/coordinates, optional geocoding; import_properties_from_dataframe is the main entry."""
from __future__ import annotations

import io
import re
from typing import Any

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

# Optional FastAPI import (only needed for async CSV upload endpoint)
try:
    from fastapi import UploadFile
except ImportError:
    UploadFile = None  # type: ignore

from app.models.property_normalized import PropertyNormalized as Property
from app.utils.constants import Defaults, CSVImportMessages
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.logger import get_logger
from app.utils.security import validate_input_length, MAX_CURRENCY_INPUT_LENGTH, MAX_AREA_INPUT_LENGTH

logger = get_logger(__name__)


# Safe regex patterns - optimized to prevent ReDoS attacks
# Using more specific patterns and avoiding nested quantifiers
# Pattern 1: Currency symbol followed by digits (most common case)
# Pattern 2: Just digits (fallback)
# Made safer by limiting repetition and avoiding nested quantifiers
CURRENCY_RE = re.compile(
    r"(?:([a-z]{3}|[$€£])\s*)?(\d{1,20}(?:[.,]\d{0,10})?)",
    re.IGNORECASE
)
# Pattern: Simple numeric pattern with explicit length limits
AREA_RE = re.compile(r"(\d{1,20}(?:[.,]\d{0,10})?)")


def _parse_area(value: Any) -> float | None:
    """
    Parse area value, extracting numeric part from strings like '400 Sqm'.
    Includes input validation to prevent ReDoS attacks.
    """
    if value is None:
        return None
    
    try:
        # Validate and limit input length to prevent ReDoS
        text = validate_input_length(str(value), MAX_AREA_INPUT_LENGTH)
    except (ValueError, TypeError):
        return None
    
    if not text.strip():
        return None
    
    # Try to extract numeric value with safe regex
    m = AREA_RE.search(text)
    if m:
        # Get the first non-None group
        num_str = next((g for g in m.groups() if g is not None), None)
        if num_str:
            num_str = num_str.replace(",", "")
            try:
                return float(num_str)
            except ValueError:
                return None
    return None


def _parse_int(value: Any) -> int | None:
    """
    Safely parse integer value, handling invalid strings.
    Includes input validation to prevent ReDoS attacks.
    """
    if value is None:
        return None
    if pd.isna(value):
        return None
    try:
        # Try direct conversion first
        if isinstance(value, (int, float)):
            return int(value)
        # Try string conversion with length validation
        try:
            text = validate_input_length(str(value), MAX_AREA_INPUT_LENGTH)
        except (ValueError, TypeError):
            return None
        
        if not text.strip():
            return None
        
        # Safe regex: simple pattern with no nested quantifiers
        # Extract first numeric sequence (with optional minus sign)
        num_match = re.search(r'-?\d{1,20}', text)  # Limit to 20 digits max
        if num_match:
            return int(num_match.group())
        return None
    except (ValueError, TypeError, AttributeError):
        return None


def _parse_price(value: Any) -> tuple[float | None, str | None]:
    """
    Parse price value with currency.
    Includes input validation to prevent ReDoS attacks.
    """
    if value is None:
        return None, None
    
    try:
        # Validate and limit input length to prevent ReDoS
        text = validate_input_length(str(value), MAX_CURRENCY_INPUT_LENGTH)
    except (ValueError, TypeError):
        return None, None
    
    if not text.strip():
        return None, None
    
    m = CURRENCY_RE.search(text)
    if not m:
        return None, None
    
    # Group 1: Currency symbol (optional)
    # Group 2: Number (required)
    currency_match = m.group(1)
    number_match = m.group(2)
    
    if not number_match:
        return None, None
    
    num_clean = number_match.replace(",", "")
    try:
        amount = float(num_clean)
    except ValueError:
        return None, None

    currency = None
    if currency_match:
        cur_upper = currency_match.upper()
        if cur_upper in {"USD", "EUR", "GBP", "JOD"}:
            currency = cur_upper
        elif currency_match == "$":
            currency = "USD"
        elif currency_match == "€":
            currency = "EUR"
        elif currency_match == "£":
            currency = "GBP"
    
    # Also check if "JOD" appears anywhere in the text (common format: "30,000 JOD")
    if currency is None and "JOD" in text.upper():
        currency = "JOD"
    
    return amount, currency


def _split_pipe(value: Any) -> list[str]:
    if value is None:
        return []
    parts = str(value).split("|")
    return [p.strip() for p in parts if p.strip()]


def _normalize_string(value: Any) -> str | None:
    """Normalize string value from CSV row, converting NaN to None."""
    if value is None or pd.isna(value):
        return None
    value_str = str(value).strip()
    if value_str.lower() in ("nan", "none", ""):
        return None
    return value_str


def _normalize_location_name(location_name: Any) -> str | None:
    """Normalize location name from CSV row."""
    if location_name is None or pd.isna(location_name):
        return None
    location_name_str = str(location_name).strip()
    if location_name_str.lower() in ("nan", "none", ""):
        return None
    return location_name_str


def _parse_single_coordinate(value) -> float | None:
    """Parse a single coordinate value, handling NaN and infinity."""
    if value is None or pd.isna(value):
        return None
    try:
        coord_val = float(value)
        if pd.isna(coord_val) or coord_val == float('inf') or coord_val == float('-inf'):
            return None
        return coord_val
    except (TypeError, ValueError):
        return None


def _geocode_missing_coordinates(
    row: pd.Series, 
    lat_f: float | None, 
    lng_f: float | None,
    geocode_missing: bool,
    geocoding_service
) -> tuple[float | None, float | None]:
    """Geocode coordinates if they are missing."""
    if lat_f is not None and lng_f is not None:
        return lat_f, lng_f
    
    if not geocode_missing or not geocoding_service:
        return lat_f, lng_f
    
    location = row.get("location")
    if not location or pd.isna(location):
        return lat_f, lng_f
    
    coords = geocoding_service.get_coordinates_with_fallback(str(location))
    if coords:
        lng_f, lat_f = coords  # Nominatim returns (lon, lat)
    
    return lat_f, lng_f


def _parse_coordinates(row: pd.Series, geocode_missing: bool, geocoding_service) -> tuple[float | None, float | None]:
    """Parse coordinates from row, optionally geocoding if missing."""
    lat = row.get("latitude")
    lng = row.get("longitude")
    
    lat_f = _parse_single_coordinate(lat)
    lng_f = _parse_single_coordinate(lng)
    
    return _geocode_missing_coordinates(row, lat_f, lng_f, geocode_missing, geocoding_service)


def _parse_title(row: pd.Series) -> str:
    """Parse and normalize title from row."""
    title_raw = row.get("property_name") or row.get("title")
    if title_raw is None or pd.isna(title_raw) or str(title_raw).lower() in ("nan", "none", ""):
        return Defaults.UNTITLED_PROPERTY
    return str(title_raw).strip()


def _update_existing_property(
    existing_prop: Property,
    row: pd.Series,
    lat_f: float | None,
    lng_f: float | None,
    db: Session
) -> bool:
    """Update existing property with coordinates and location_name. Returns True if updated."""
    needs_update = False
    
    # Update coordinates if they're missing in DB but present in CSV
    if (existing_prop.latitude is None or existing_prop.longitude is None) and (lat_f is not None and lng_f is not None):
        existing_prop.latitude = lat_f
        existing_prop.longitude = lng_f
        if lat_f is not None and lng_f is not None:
            existing_prop.location = func.ST_SetSRID(
                func.ST_MakePoint(lng_f, lat_f),
                4326,
            )
        needs_update = True
    
    # Always update location_name if it's missing in DB
    location_name_str = _normalize_location_name(row.get("location"))
    if (existing_prop.location_name is None or existing_prop.location_name == "") and location_name_str:
        existing_prop.location_name = location_name_str
        needs_update = True
    
    if needs_update:
        db.add(existing_prop)
    
    return needs_update


def _create_property_from_row(
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
    features: list[str],
    more_features: list[str],
) -> Property:
    """Create a Property object from a CSV row."""
    location_name_str = _normalize_location_name(row.get("location"))
    
    prop = Property(
        url=url if url else None,
        title=title,
        description=_normalize_string(row.get("description")),
        category=_normalize_string(row.get("category")),
        status=_normalize_string(row.get("status")),
        selling_price_amount=selling_amount,
        selling_price_currency=selling_currency,
        rent_price_amount=rent_amount,
        rent_price_currency=rent_currency,
        bedrooms=_parse_int(row.get("bedrooms")),
        bathrooms=_parse_int(row.get("bathrooms")),
        built_up_area=_parse_area(row.get("built_up_area")),
        features=features,
        more_features=more_features,
        images=images,
        latitude=lat_f,
        longitude=lng_f,
        location_name=location_name_str,
    )

    if lat_f is not None and lng_f is not None:
        prop.location = func.ST_SetSRID(
            func.ST_MakePoint(lng_f, lat_f),
            4326,
        )
    
    return prop


def _commit_updates(db: Session, updated_count: int) -> int:
    """Commit property updates and return actual updated count."""
    if updated_count == 0:
        return 0
    
    try:
        db.commit()
        msg = format_log_message(CSVImportMessages.UPDATED_PROPERTIES, count=updated_count)
        logger.info(msg)
        return updated_count
    except Exception as e:
        db.rollback()
        msg = format_log_message(CSVImportMessages.ERROR_UPDATING, error=str(e))
        logger.error(msg)
        return 0


def _handle_empty_records(skipped_duplicates: int, updated_count: int) -> int:
    """Handle case when no new records to import."""
    if skipped_duplicates > 0 and updated_count == 0:
        msg = format_log_message(CSVImportMessages.ALL_DUPLICATES, count=skipped_duplicates)
        logger.info(msg)
    elif updated_count > 0:
        msg = format_log_message(CSVImportMessages.UPDATED_AND_SKIPPED, updated=updated_count, skipped=skipped_duplicates)
        logger.info(msg)
    return updated_count


def _insert_records_batch(
    db: Session,
    records: list[Property],
    updated_count: int,
    skipped_duplicates: int
) -> int:
    """Insert records in batch, with fallback to individual inserts on duplicate errors."""
    try:
        db.add_all(records)
        db.commit()
        imported_count = len(records)
        _print_import_summary(imported_count, updated_count, skipped_duplicates)
        return imported_count + updated_count
    except Exception as e:
        db.rollback()
        if "uq_properties_url" in str(e) or "duplicate key" in str(e).lower():
            return _insert_records_individually(db, records, skipped_duplicates)
        raise


def _insert_records_individually(
    db: Session,
    records: list[Property],
    skipped_duplicates: int
) -> int:
    """Insert records one by one, skipping duplicates."""
    logger.warning(LogMessages.CSVImport.BATCH_INSERT_FAILED)
    imported_count = 0
    
    for prop in records:
        try:
            if prop.url:
                existing = db.execute(
                    select(Property).where(Property.url == prop.url)
                ).scalar_one_or_none()
                if existing:
                    skipped_duplicates += 1
                    continue
            db.add(prop)
            db.commit()
            imported_count += 1
        except Exception as individual_error:
            db.rollback()
            if "uq_properties_url" in str(individual_error) or "duplicate key" in str(individual_error).lower():
                skipped_duplicates += 1
                continue
            raise
    
    if skipped_duplicates > 0:
        msg = format_log_message(CSVImportMessages.IMPORTED_SKIPPED, imported=imported_count, skipped=skipped_duplicates)
        logger.info(msg)
    return imported_count


def _print_import_summary(imported_count: int, updated_count: int, skipped_duplicates: int) -> None:
    """Log import summary message using utils messages."""
    if imported_count == 0 and updated_count == 0 and skipped_duplicates == 0:
        return
    summary = format_log_message(
        CSVImportMessages.IMPORTED_UPDATED_SKIPPED,
        imported=imported_count,
        updated=updated_count,
        skipped=skipped_duplicates,
    )
    msg = format_log_message(LogMessages.CSVImport.IMPORTED_UPDATED_SKIPPED, summary=summary)
    logger.info(msg)


def import_properties_from_dataframe(
    db: Session,
    df: pd.DataFrame,
    geocode_missing: bool = False,
    skip_duplicates: bool = True,
    update_coordinates: bool = False,
) -> int:
    """
    Import properties from DataFrame into database.
    
    Args:
        db: Database session
        df: DataFrame containing property data
        geocode_missing: If True, geocode locations that don't have coordinates
        skip_duplicates: If True, skip properties that already exist (by URL)
        update_coordinates: If True, update coordinates for existing properties that have missing coordinates
    """
    records: list[Property] = []
    skipped_duplicates = 0
    updated_count = 0

    # Import geocoding service only if needed
    geocoding_service = _get_geocoding_service(geocode_missing)

    # Pre-fetch existing properties for duplicate checking and updates
    existing_properties = _load_existing_properties(db, skip_duplicates, update_coordinates)

    for _, row in df.iterrows():
        # Parse row data
        (selling_amount, selling_currency, rent_amount, rent_currency,
         images, features, more_features, lat_f, lng_f, title, url) = _parse_row_data(
            row, geocode_missing, geocoding_service
        )
        
        # Handle existing properties
        existing_prop = existing_properties.get(url) if url else None
        if existing_prop:
            should_continue, update_inc, skip_inc = _handle_existing_property(
                existing_prop, row, lat_f, lng_f,
                update_coordinates, skip_duplicates, db
            )
            if should_continue:
                updated_count += update_inc
                skipped_duplicates += skip_inc
                continue
        
        # Create new property
        prop = _create_property_from_row(
            row, url, title, lat_f, lng_f,
            selling_amount, selling_currency, rent_amount, rent_currency,
            images, features, more_features
        )
        
        records.append(prop)
        if url:
            existing_properties[url] = prop

    # Commit updates
    updated_count = _commit_updates(db, updated_count)

    # Handle empty records
    if not records:
        return _handle_empty_records(skipped_duplicates, updated_count)

    # Insert new records
    return _insert_records_batch(db, records, updated_count, skipped_duplicates)


def _get_geocoding_service(geocode_missing: bool):
    """Get geocoding service if needed."""
    if not geocode_missing:
        return None
    try:
        from app.services.geocoding import geocoding_service
        return geocoding_service
    except ImportError:
        logger.warning(LogMessages.CSVImport.GEOCODING_UNAVAILABLE)
        return None


def _load_existing_properties(db: Session, skip_duplicates: bool, update_coordinates: bool) -> dict[str, Property]:
    """Load existing properties from database if needed."""
    if not (skip_duplicates or update_coordinates):
        return {}
    existing_props = db.execute(select(Property)).scalars().all()
    return {prop.url: prop for prop in existing_props if prop.url}


def _parse_row_data(row: pd.Series, geocode_missing: bool, geocoding_service) -> tuple:
    """Parse all data from a CSV row."""
    selling_amount, selling_currency = _parse_price(row.get("selling_price"))
    rent_amount, rent_currency = _parse_price(row.get("rent_price"))
    images = _split_pipe(row.get("image_urls"))
    features = _split_pipe(row.get("features"))
    more_features = _split_pipe(row.get("more_features"))
    lat_f, lng_f = _parse_coordinates(row, geocode_missing, geocoding_service)
    title = _parse_title(row)
    url = str(row.get("url") or row.get("id") or "").strip()
    return (selling_amount, selling_currency, rent_amount, rent_currency,
            images, features, more_features, lat_f, lng_f, title, url)


def _handle_existing_property(
    existing_prop: Property,
    row: pd.Series,
    lat_f: float | None,
    lng_f: float | None,
    update_coordinates: bool,
    skip_duplicates: bool,
    db: Session
) -> tuple[bool, int, int]:
    """
    Handle existing property logic.
    Returns: (should_continue, updated_count, skipped_count)
    """
    if update_coordinates:
        if _update_existing_property(existing_prop, row, lat_f, lng_f, db):
            return (True, 1, 0)
    
    if skip_duplicates:
        return (True, 0, 1)
    
    return (False, 0, 0)


async def import_properties_from_csv_file(
    db: Session,
    upload: "UploadFile",  # type: ignore
    geocode_missing: bool = False,
) -> int:
    """
    Import properties from CSV file.
    
    Args:
        db: Database session
        upload: Uploaded CSV file
        geocode_missing: If True, geocode locations that don't have coordinates
    """
    content = await upload.read()
    df = pd.read_csv(io.BytesIO(content))
    return import_properties_from_dataframe(db, df, geocode_missing=geocode_missing)


