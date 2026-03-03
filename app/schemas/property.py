"""
Property schemas for API request/response models.

This module defines Pydantic models for property-related API operations,
including search results, property details, search requests, and responses.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
import json
import hashlib

from pydantic import BaseModel, Field, model_serializer
from sqlalchemy import select, func
from sqlalchemy.orm import Session

import uuid
from app.models.property_normalized import PropertyNormalized as Property
from app.utils.constants import Defaults
from app.services.translation_service import (
    get_title_description_for_language,
    get_title_description_all_languages,
    get_address_all_languages,
)

# Feature keys from CSV more_features that carry a value (appear in structured slots, not in amenities)
FEATURE_VALUE_KEYS = {
    "Finishing",
    "Windows",
    "Window Shutters",
    "Doors",
    "Air Conditioning",
    "Heating System",
    "Heating Fuel",
}

# Meta fields stored as Feature + value; used in general/details only, not in features.amenities
META_FEATURE_NAMES = {
    "Floor Type",
    "Floor",
    "Building Status",
    "Garage",
    "Terrace Area",
    "Garden Area",
    "Master Bedrooms",
    "Kitchens",
    "Furniture",
}

# Feature names that are value literals (e.g. "Standard", "Deluxe"); do not list in amenities
FEATURE_VALUE_LIKE_NAMES = {
    "Standard",
    "Double Glazed",
    "Electric",
    "Manual",
    "Central",
    "Split Units",
    "Underfloor",
    "Radiators",
    "Diesel",
    "Gas",
    "Firewood",
    "Deluxe",
    "Full",
    "Partial",
    "Yes",
    "Safety Doors",
}


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


class PropertyLocationDetail(BaseModel):
    """Nested location for API: country, city, region, address, coordinates, map link."""
    country_id: Optional[int] = 1  # Jordan
    country: Optional[str] = "Jordan"
    city_id: Optional[int] = None
    city: Optional[str] = None
    region_id: Optional[int] = None
    region: Optional[str] = None
    address: Optional[dict[str, str]] = None  # e.g. {"en": "Abdoun - Amman", "ar": "...", "esp": "...", "fr": "..."}
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    map_embed_url: Optional[str] = None  # https://maps.google.com/?q=lat,lng


class PropertyGeneralStructured(BaseModel):
    """
    General info block for detail response (guide format).
    All fields from CSV/DB where available; null otherwise.
    """
    floor_type: Optional[str] = None
    floor_number: Optional[int] = None
    building_status: Optional[str] = None
    built_in_year: Optional[int] = None
    furniture_status: Optional[str] = None
    furniture_condition: Optional[str] = None
    garage_type: Optional[str] = None
    total_floors_in_building: Optional[int] = None


class PropertyDetailsStructured(BaseModel):
    """
    Details block for detail response (guide format).
    built_up_area, land_area, bedrooms, bathrooms from DB; maid/driver/store_rooms derived from features.
    terrace_area, garden_area, master_bedrooms, kitchens from DB or from meta features (Feature.value).
    """
    built_up_area: Optional[float] = None
    land_area: Optional[float] = None
    garden_area: Optional[float] = None
    terrace_area: Optional[float] = None
    area_unit: Optional[str] = None
    bedrooms: Optional[int] = None
    master_bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    living_rooms: Optional[int] = None
    salons: Optional[int] = None
    balconies: Optional[int] = None
    entrances: Optional[int] = None
    kitchens: Optional[int] = None
    kitchen_type: Optional[str] = None
    maid_rooms: Optional[int] = None
    driver_rooms: Optional[int] = None
    store_rooms: Optional[int] = None


class PropertyFeaturesStructured(BaseModel):
    """
    Structured features object for detail response. Only keys with a value are
    included in JSON (null and empty list are omitted).
    """
    amenities: list[str] = []
    finishing: Optional[str] = None
    windows: Optional[str] = None
    window_shutters: Optional[str] = None
    doors: Optional[str] = None
    air_conditioning: Optional[str] = None
    heating_system: Optional[str] = None
    heating_fuel: Optional[str] = None
    has_view: Optional[bool] = None
    view_type: list[str] = []

    @model_serializer(mode="wrap")
    def _serialize_omit_empty(self, serializer):
        """Omit keys with None or empty list so they don't appear in the response."""
        data = serializer(self)
        return {k: v for k, v in data.items() if v is not None and v != []}


class PropertyPricingStructured(BaseModel):
    """
    Pricing block per guide: listing_type, rents, selling_price, currency, commission, etc.
    Built from CSV/DB: selling_price, rent_price (and optional rent_commission, payment_method).
    Keys with null/empty are omitted in the response.
    """
    listing_type: Optional[str] = None  # "sale" | "rent" | "sale_rent"
    annual_rent: Optional[float] = None
    monthly_rent: Optional[float] = None
    quarterly_rent: Optional[float] = None
    selling_price: Optional[float] = None
    currency: Optional[str] = None
    price_on_request: Optional[bool] = None
    rent_commission_percent: Optional[float] = None
    contract_duration: Optional[str] = None
    contract_duration_unit: Optional[str] = None
    payment_method: Optional[str] = None
    is_negotiable: Optional[bool] = None
    down_payment: Optional[float] = None
    installment_available: Optional[bool] = None
    installment_details: Optional[str] = None

    @model_serializer(mode="wrap")
    def _serialize_omit_empty(self, serializer):
        data = serializer(self)
        required_pricing_keys = {
            "rent_commission_percent",
            "contract_duration",
            "payment_method",
        }
        return {
            k: v
            for k, v in data.items()
            if (k in required_pricing_keys) or (v is not None and v != [])
        }


class PropertyMediaItem(BaseModel):
    id: int
    url: str
    thumb_url: Optional[str] = None
    is_primary: bool = False
    order: int = 0
    caption: Optional[str] = None


class PropertyMediaStructured(BaseModel):
    thumbnail: Optional[str] = None
    images: list[PropertyMediaItem] = Field(default_factory=list)
    videos: list[PropertyMediaItem] = Field(default_factory=list)
    virtual_tour_url: Optional[str] = None
    floor_plan_images: list[PropertyMediaItem] = Field(default_factory=list)
    documents: list[PropertyMediaItem] = Field(default_factory=list)


class PropertyAgentMock(BaseModel):
    id: int
    name: str
    phone: str
    whatsapp: str
    email: str
    photo: Optional[str] = None
    license_number: Optional[str] = None


class PropertyOwnerMock(BaseModel):
    id: int
    name: str
    phone: str
    email: str
    is_private: bool = False


class PropertyCreatedByMock(BaseModel):
    id: int
    name: str
    role: str


def get_mock_agent() -> PropertyAgentMock:
    return PropertyAgentMock(
        id=3,
        name="Ahmed Al-Khalidi",
        phone="+962799000000",
        whatsapp="+962799000000",
        email="ahmed@example.com",
        photo="https://cdn.example.com/agents/3/photo.jpg",
        license_number="RE-0042",
    )


def get_mock_owner() -> PropertyOwnerMock:
    return PropertyOwnerMock(
        id=55,
        name="Mohammad Tarawneh",
        phone="+962790000000",
        email="owner@example.com",
        is_private=False,
    )


def get_mock_created_by() -> PropertyCreatedByMock:
    return PropertyCreatedByMock(
        id=2,
        name="Admin Sarah",
        role="super_admin",
    )


def _determine_listing_type(obj: Property) -> str:
    """Derive listing_type from selling/rent prices (CSV: selling_price, rent_price)."""
    has_selling = getattr(obj, "selling_price_amount", None) is not None
    has_rent = getattr(obj, "rent_price_amount", None) is not None
    if has_selling and has_rent:
        return "sale_rent"
    if has_selling:
        return "sale"
    if has_rent:
        return "rent"
    return "rent"  # default when no price


def _parse_images_list_from_orm(obj: Property) -> list[str]:
    """Return legacy images list from old/new model field."""
    images_list: list[str] = []
    if hasattr(obj, "images"):
        if isinstance(obj.images, str):
            try:
                images_list = json.loads(obj.images)
            except Exception:
                images_list = []
        elif isinstance(obj.images, list):
            images_list = obj.images
    return [str(u).strip() for u in images_list if u and str(u).strip()]


def _build_media_from_orm(obj: Property) -> PropertyMediaStructured:
    """Build structured media block from property_media with fallback to legacy images."""
    images: list[PropertyMediaItem] = []
    videos: list[PropertyMediaItem] = []
    floor_plans: list[PropertyMediaItem] = []
    documents: list[PropertyMediaItem] = []
    thumbnail: Optional[str] = None

    # Only use media_items when already loaded to avoid implicit DB queries.
    media_rows = list(getattr(obj, "__dict__", {}).get("media_items") or [])
    if media_rows:
        media_rows.sort(key=lambda m: (getattr(m, "display_order", 0) or 0, getattr(m, "id", 0) or 0))
        for idx, m in enumerate(media_rows, start=1):
            item = PropertyMediaItem(
                id=int(getattr(m, "id", idx) or idx),
                url=str(getattr(m, "url", "") or ""),
                thumb_url=(getattr(m, "thumb_url", None) or getattr(m, "url", None)),
                is_primary=bool(getattr(m, "is_primary", False)),
                order=int(getattr(m, "display_order", idx) or idx),
                caption=getattr(m, "caption", None),
            )
            if not item.url:
                continue
            media_type = (getattr(m, "media_type", "image") or "image").strip().lower()
            if media_type == "video":
                videos.append(item)
            elif media_type == "floor_plan":
                floor_plans.append(item)
            elif media_type == "document":
                documents.append(item)
            else:
                images.append(item)

        primary_image = next((img for img in images if img.is_primary), None)
        if primary_image:
            thumbnail = primary_image.thumb_url or primary_image.url
        elif images:
            thumbnail = images[0].thumb_url or images[0].url
    else:
        # Backward-compatible fallback while old images column still exists.
        legacy_images = _parse_images_list_from_orm(obj)
        for idx, url in enumerate(legacy_images, start=1):
            images.append(
                PropertyMediaItem(
                    id=idx,
                    url=url,
                    thumb_url=url,
                    is_primary=(idx == 1),
                    order=idx,
                    caption=None,
                )
            )
        if images:
            thumbnail = images[0].thumb_url or images[0].url

    return PropertyMediaStructured(
        thumbnail=thumbnail,
        images=images,
        videos=videos,
        virtual_tour_url=None,
        floor_plan_images=floor_plans,
        documents=documents,
    )


def _build_pricing_from_orm(obj: Property) -> Optional[PropertyPricingStructured]:
    """
    Build pricing from properties_normalized: selling_price_amount/currency, rent_price_amount/currency.
    CSV: selling_price ("JOD 320,000"), rent_price ("30,000 JOD"), rent_commission ("5.00 %"), payment_method ("Annual").
    """
    if not hasattr(obj, "selling_price_amount") or not hasattr(obj, "rent_price_amount"):
        return None
    selling = getattr(obj, "selling_price_amount", None)
    rent = getattr(obj, "rent_price_amount", None)
    currency = (
        getattr(obj, "currency", None)
        or getattr(obj, "rent_price_currency", None)
        or getattr(obj, "selling_price_currency", None)
        or "JOD"
    )

    annual_rent = float(rent) if rent is not None else None
    monthly_rent = (annual_rent / 12.0) if annual_rent else None
    quarterly_rent = (annual_rent / 4.0) if annual_rent else None
    selling_price = float(selling) if selling is not None else None

    rent_commission_percent = getattr(obj, "rent_commission_percent", None)
    if rent_commission_percent is not None:
        rent_commission_percent = float(rent_commission_percent)
    contract_duration_raw = getattr(obj, "contract_duration", None)
    contract_duration_val = None
    if contract_duration_raw and str(contract_duration_raw).strip().lower() not in ("undefined", "nan", "none", ""):
        contract_duration_val = str(contract_duration_raw).strip()
    payment_method_raw = getattr(obj, "payment_method", None)
    payment_method_val = None
    if payment_method_raw and str(payment_method_raw).strip().lower() not in ("undefined", "nan", "none", ""):
        payment_method_val = str(payment_method_raw).strip().lower()

    return PropertyPricingStructured(
        listing_type=_determine_listing_type(obj),
        annual_rent=annual_rent,
        monthly_rent=round(monthly_rent, 2) if monthly_rent is not None else None,
        quarterly_rent=round(quarterly_rent, 2) if quarterly_rent is not None else None,
        selling_price=selling_price,
        currency=currency,
        price_on_request=False,
        rent_commission_percent=rent_commission_percent,
        contract_duration=contract_duration_val,
        contract_duration_unit=None,
        payment_method=payment_method_val,
        is_negotiable=False,
        down_payment=None,
        installment_available=False,
        installment_details=None,
    )


def _normalize_furniture_status(raw: Optional[str]) -> Optional[str]:
    """Map furniture_status from DB/CSV to guide format (e.g. furnished, unfurnished)."""
    if not raw or not str(raw).strip():
        return None
    v = str(raw).strip().lower()
    if "furnish" in v or v == "furnished":
        return "furnished"
    if "unfurnish" in v or v == "unfurnished":
        return "unfurnished"
    return v.replace(" ", "_")


def _normalize_floor_type(raw: Optional[str]) -> Optional[str]:
    """Map CSV type / Floor Type to guide slug (ground, upper, semi_ground, roof, detached, etc.)."""
    if not raw or not str(raw).strip():
        return None
    v = str(raw).strip().lower()
    if "ground" in v and "semi" not in v:
        return "ground"
    if "semi" in v and "ground" in v:
        return "semi_ground"
    if "upper" in v or "floor" in v:
        return "upper"
    if "roof" in v:
        return "roof"
    if "detached" in v and "semi" not in v:
        return "detached"
    if "semi" in v and "detach" in v:
        return "semi_detached"
    return v.replace(" ", "_")


def _normalize_building_status(raw: Optional[str]) -> Optional[str]:
    """Map Building Status to used/new."""
    if not raw or not str(raw).strip():
        return None
    v = str(raw).strip().lower()
    if v == "new":
        return "new"
    return "used"


def _normalize_garage_type(raw: Optional[str]) -> Optional[str]:
    """Map Garage to closed/open."""
    if not raw or not str(raw).strip():
        return None
    v = str(raw).strip().lower()
    if v == "open":
        return "open"
    if v == "closed":
        return "closed"
    return v


def _build_general_from_orm(obj: Property) -> Optional[PropertyGeneralStructured]:
    """Build general block from DB columns and from meta features (Floor Type, Floor, Building Status, Garage, Furniture)."""
    furniture_status = _normalize_furniture_status(getattr(obj, "furniture_status", None))
    if not furniture_status and hasattr(obj, "features"):
        furniture_status = _normalize_furniture_status(_get_feature_value_by_name(obj, "Furniture"))
    property_age = getattr(obj, "property_age", None)
    built_in_year = int(property_age) if property_age is not None else None

    floor_type = floor_number = building_status = garage_type = None
    if hasattr(obj, "features") and obj.features:
        ft_val = _get_feature_value_by_name(obj, "Floor Type")
        floor_type = _normalize_floor_type(ft_val) if ft_val else None
        floor_val = _get_feature_value_by_name(obj, "Floor")
        if floor_val is not None:
            try:
                floor_number = int(float(floor_val))
            except (ValueError, TypeError):
                pass
        building_status = _normalize_building_status(_get_feature_value_by_name(obj, "Building Status"))
        garage_type = _normalize_garage_type(_get_feature_value_by_name(obj, "Garage"))

    if not (furniture_status or built_in_year or floor_type or floor_number is not None or building_status or garage_type):
        return None
    return PropertyGeneralStructured(
        floor_type=floor_type,
        floor_number=floor_number,
        building_status=building_status,
        built_in_year=built_in_year,
        furniture_status=furniture_status,
        furniture_condition=None,
        garage_type=garage_type,
        total_floors_in_building=None,
    )


def _get_feature_value_by_name(obj: Property, feature_name: str) -> Optional[str]:
    """Return PropertyFeature.value for the first feature whose name equals feature_name (case-sensitive match)."""
    if not hasattr(obj, "features") or not obj.features or not feature_name:
        return None
    for pf in obj.features:
        feature = getattr(pf, "feature", None)
        if not feature:
            continue
        if (getattr(feature, "name", None) or "").strip() == feature_name.strip():
            val = getattr(pf, "value", None)
            return str(val).strip() if val and str(val).strip() and str(val).lower() not in ("nan", "none") else None
    return None


def _count_feature_by_name(obj: Property, name_patterns: list[str]) -> int:
    """Return 1 if property has a feature whose name matches any of the patterns, else 0."""
    if not hasattr(obj, "features") or not obj.features:
        return 0
    for pf in obj.features:
        feature = getattr(pf, "feature", None)
        if not feature:
            continue
        name = (getattr(feature, "name", None) or "").strip().lower()
        for pattern in name_patterns:
            if pattern.lower() in name or name in pattern.lower():
                return 1
    return 0


def _parse_float_from_feature(val: Optional[str]) -> Optional[float]:
    """Parse a numeric string from feature value to float."""
    if not val or not str(val).strip():
        return None
    try:
        return float(str(val).strip())
    except (ValueError, TypeError):
        return None


def _parse_int_from_feature(val: Optional[str]) -> Optional[int]:
    """Parse a numeric string from feature value to int."""
    if not val or not str(val).strip():
        return None
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return None


def _build_details_from_orm(obj: Property) -> Optional[PropertyDetailsStructured]:
    """Build details block from DB columns and meta features (Terrace Area, Garden Area, Master Bedrooms, Kitchens)."""
    if not hasattr(obj, "area") and not hasattr(obj, "bedrooms"):
        return None
    built_up = float(obj.area) if getattr(obj, "area", None) is not None else None
    land = float(obj.plot_area) if getattr(obj, "plot_area", None) is not None else None
    maid_rooms = _count_feature_by_name(obj, ["Maid's Room", "Maids Room", "maid room"])
    driver_rooms = _count_feature_by_name(obj, ["Driver's Room", "Drivers Room", "driver room"])
    store_rooms = _count_feature_by_name(obj, ["Storage Room", "Store Room", "storage room", "store room"])

    garden_area = terrace_area = master_bedrooms = kitchens = None
    if hasattr(obj, "features") and obj.features:
        garden_area = _parse_float_from_feature(_get_feature_value_by_name(obj, "Garden Area"))
        terrace_area = _parse_float_from_feature(_get_feature_value_by_name(obj, "Terrace Area"))
        master_bedrooms = _parse_int_from_feature(_get_feature_value_by_name(obj, "Master Bedrooms"))
        kitchens = _parse_int_from_feature(_get_feature_value_by_name(obj, "Kitchens"))

    return PropertyDetailsStructured(
        built_up_area=built_up,
        land_area=land,
        garden_area=garden_area,
        terrace_area=terrace_area,
        area_unit="sqm",
        bedrooms=getattr(obj, "bedrooms", None),
        master_bedrooms=master_bedrooms,
        bathrooms=getattr(obj, "bathrooms", None),
        living_rooms=getattr(obj, "rooms", None),
        salons=None,
        balconies=None,
        entrances=None,
        kitchens=kitchens,
        kitchen_type=None,
        maid_rooms=maid_rooms or None,
        driver_rooms=driver_rooms or None,
        store_rooms=store_rooms or None,
    )


def _normalize_amenity_slug(name: str, slug: Optional[str] = None) -> str:
    """
    Normalize a feature name/slug to amenity slug like 'maid_room', 'laundry_room'.
    Uses DB slug when available, otherwise falls back to name.
    """
    base = (slug or name or "").strip().lower()
    # Unify separators and remove apostrophes
    base = base.replace("’", "").replace("'", "")
    base = base.replace("/", "-").replace(" ", "-")
    return base.replace("-", "_")


def _normalize_feature_value(val: str) -> str:
    """Normalize a feature value to slug-like form (lowercase, spaces to underscores)."""
    if not val or not str(val).strip():
        return ""
    v = str(val).strip().lower()
    return v.replace(" ", "_")


def _build_structured_features(
    obj: Property,
    more_features: Optional[dict[str, Any]] = None,
) -> Optional[PropertyFeaturesStructured]:
    """
    Build features from two sources only (no redundant paths):
    - Value slots (finishing, windows, ...): from properties_normalized.more_features JSON only.
    - Amenities: from Property.features relationship (CSV "features" column, amenities only).
    """
    if not hasattr(obj, "features"):
        return None

    amenities: list[str] = []
    has_view: Optional[bool] = None
    view_type: list[str] = []
    mf = more_features or {}

    # Value slots: single source = more_features JSON (from DB column)
    finishing = _normalize_feature_value(str(mf["Finishing"])) if mf.get("Finishing") else None
    windows = _normalize_feature_value(str(mf["Windows"])) if mf.get("Windows") else None
    window_shutters = _normalize_feature_value(str(mf["Window Shutters"])) if mf.get("Window Shutters") else None
    doors = _normalize_feature_value(str(mf["Doors"])) if mf.get("Doors") else None
    air_conditioning = _normalize_feature_value(str(mf["Air Conditioning"])) if mf.get("Air Conditioning") else None
    heating_system = _normalize_feature_value(str(mf["Heating System"])) if mf.get("Heating System") else None
    heating_fuel = _normalize_feature_value(str(mf["Heating Fuel"])) if mf.get("Heating Fuel") else None

    # Amenities only: from Property.features (exclude value keys, meta, value-like)
    for pf in (obj.features or []):
        feature = getattr(pf, "feature", None)
        if not feature:
            continue
        name = getattr(feature, "name", None) or ""
        if name in FEATURE_VALUE_KEYS or name in META_FEATURE_NAMES or name in FEATURE_VALUE_LIKE_NAMES:
            continue
        amenity_slug = _normalize_amenity_slug(name, getattr(feature, "slug", None))
        if amenity_slug and amenity_slug not in amenities:
            amenities.append(amenity_slug)
        if "view" in (amenity_slug or ""):
            has_view = True if has_view is not False else has_view
            if amenity_slug not in view_type:
                view_type.append(amenity_slug)

    return PropertyFeaturesStructured(
        amenities=amenities,
        finishing=finishing,
        windows=windows,
        window_shutters=window_shutters,
        doors=doors,
        air_conditioning=air_conditioning,
        heating_system=heating_system,
        heating_fuel=heating_fuel,
        has_view=has_view,
        view_type=view_type,
    )


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
    title and description use multi-language format: { "en": "...", "ar": "...", "esp": "...", "fr": "..." }.
    """
    id: int | str  # Support both int (old) and UUID string (normalized)
    reference_number: Optional[str] = None  # Display ref from source (e.g. CSV property_id)
    title: dict[str, str]  # e.g. {"en": "Apartment for Rent", "ar": "شقة للإيجار", "esp": "...", "fr": "..."}
    description: Optional[dict[str, Optional[str]]] = None  # e.g. {"en": "...", "ar": "...", "esp": "...", "fr": "..."}

    price: Optional[str] = None  # Formatted as "2,100 JD"
    status: Optional[str] = None  # "rent" or "buy"
    category: Optional[str] = None  # "residential", "land", etc.
    searchPropertyType: Optional[str] = None  # "Apartments", "Residential Lands"
    city: Optional[str] = None  # "Amman"
    areaName: Optional[str] = None  # "Jabal Amman", "Swefieh"
    propertyType: Optional[str] = None  # "Apartment", "Lot / Land for sale"
    media: Optional[PropertyMediaStructured] = None
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
    is_exclusive: Optional[bool] = None  # From DB; None if not available
    location: Optional[PropertyLocationDetail] = None  # Preferred key per response guide
    location_detail: Optional[PropertyLocationDetail] = None  # Nested: country, city, region, map_embed_url

    @classmethod
    def from_orm_obj(cls, obj: Property, lang: Optional[str] = None) -> "PropertySearchResultExtended":
        """
        Create PropertySearchResultExtended from a Property ORM object.

        If lang is provided (en, ar, esp, fr), title (and list-level fields) use
        property_translations for that language with fallback to property.title.
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
        
        # Title and description: multi-language objects { "en", "ar", "esp", "fr" }
        title_by_lang, description_by_lang = get_title_description_all_languages(obj)

        # Format validated date from created_at if available
        validated_date_str = None
        if obj.created_at:
            day = obj.created_at.day
            suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
            validated_date_str = f"{day}{suffix} of {obj.created_at.strftime('%B')}"
        
        media_block = _build_media_from_orm(obj)
        
        # Convert UUID to int for compatibility
        prop_id = obj.id
        if hasattr(obj, 'category_id'):  # Normalized model with UUID
            # Convert UUID to int hash for API compatibility
            if isinstance(obj.id, uuid.UUID):
                prop_id = uuid_to_int_hash(obj.id)
            elif hasattr(obj.id, '__int__'):
                prop_id = int(obj.id)
        
        # Nested location (country, city, region, map_embed_url) from existing fields
        location_detail = None
        if hasattr(obj, 'city_id') and (obj.city or obj.area_rel or obj.location_name or (obj.latitude and obj.longitude)):
            lat = float(obj.latitude) if obj.latitude is not None else None
            lng = float(obj.longitude) if obj.longitude is not None else None
            address_by_lang = get_address_all_languages(obj)
            location_detail = PropertyLocationDetail(
                country_id=1,
                country="Jordan",
                city_id=getattr(obj, 'city_id', None),
                city=obj.city.name if obj.city else None,
                region_id=getattr(obj, 'location_id', None),
                region=obj.area_rel.name if obj.area_rel else None,
                address=address_by_lang,
                latitude=lat,
                longitude=lng,
                map_embed_url=f"https://maps.google.com/?q={lat},{lng}" if (lat is not None and lng is not None) else None,
            )
        
        return cls(
            id=prop_id,
            reference_number=getattr(obj, "reference_number", None),
            title=title_by_lang,
            description=description_by_lang,
            price=price_str,
            status=status,
            category=category,
            searchPropertyType=searchPropertyType,
            city=city,
            areaName=areaName,
            propertyType=propertyType,
            media=media_block,
            location=location_detail,
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
            is_exclusive=getattr(obj, "is_exclusive", None),
            location_detail=location_detail,
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
        features: Structured { amenities, finishing, windows, ... } per guide (from CSV features + more_features)
        images: List of image URLs
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        location_name: Name of the location/area
    """
    id: int
    reference_number: Optional[str] = None  # Display ref from source (e.g. CSV property_id)
    url: Optional[str] = None
    title: dict[str, str]  # e.g. {"en": "Apartment for Rent", "ar": "شقة للإيجار", "esp": "...", "fr": "..."}
    description: Optional[dict[str, Optional[str]]] = None  # e.g. {"en": "...", "ar": "...", "esp": "...", "fr": "..."}
    category: Optional[str] = None
    property_type: Optional[str] = None
    status: Optional[str] = None
    listing_type: Optional[str] = None  # "sale" | "rent" | "sale_rent"
    selling_price_amount: Optional[float] = None
    selling_price_currency: Optional[str] = None
    rent_price_amount: Optional[float] = None
    rent_price_currency: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    built_up_area: Optional[float] = None
    # Omitted for normalized: structured features cover CSV features + more_features; kept for legacy model
    more_features: Optional[dict[str, Any]] = None
    media: Optional[PropertyMediaStructured] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None
    is_exclusive: Optional[bool] = None  # From DB; None if not available
    location_detail: Optional[PropertyLocationDetail] = None  # Nested: country, city, region, map_embed_url
    # Structured blocks matching guide format (guide § New Format)
    general: Optional[PropertyGeneralStructured] = None
    details: Optional[PropertyDetailsStructured] = None
    features: Optional[PropertyFeaturesStructured] = None
    pricing: Optional[PropertyPricingStructured] = None  # listing_type, annual_rent, selling_price, currency, etc.
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    sold_at: Optional[datetime] = None
    rented_at: Optional[datetime] = None
    agent: Optional[PropertyAgentMock] = None
    owner: Optional[PropertyOwnerMock] = None
    created_by: Optional[PropertyCreatedByMock] = None

    @classmethod
    def from_orm_obj(cls, obj: Property, lang: Optional[str] = None) -> "PropertyDetail":
        """
        Create PropertyDetail from a Property ORM object.
        title and description are returned as multi-language objects:
        {"en": "...", "ar": "...", "esp": "...", "fr": "..."}.
        """
        title_by_lang, description_by_lang = get_title_description_all_languages(obj)

        # Handle normalized model vs old model
        if hasattr(obj, 'category_id'):  # Normalized model
            # Get category and status from relationships
            category_name = obj.category.name if obj.category else None
            property_type_name = obj.type.name if obj.type else None
            status_name = obj.property_status.name if obj.property_status else None
            
            # Parse images from JSON string
            # images_list = []
            # if obj.images:
            #     try:
            #         import json
            #         images_list = json.loads(obj.images) if isinstance(obj.images, str) else obj.images
            #     except:
            #         images_list = []
            
            # Get more_features from JSON column (already in key-value format as dict)
            more_features_dict = obj.more_features if hasattr(obj, 'more_features') and obj.more_features else None
            
            # Convert UUID to int for compatibility
            prop_id = obj.id
            if isinstance(obj.id, uuid.UUID):
                prop_id = uuid_to_int_hash(obj.id)
            
            built_up_area = float(obj.area) if obj.area is not None else None
        else:  # Old model
            category_name = getattr(obj, 'category', None)
            property_type_name = getattr(obj, 'property_type', None) or getattr(obj, 'type', None)
            status_name = getattr(obj, 'status', None)
            # images_list = obj.images or []
            more_features_list = obj.more_features or []
            prop_id = obj.id
            built_up_area = float(obj.built_up_area) if obj.built_up_area is not None else None

        # Structured blocks (general, details, features) for normalized model
        general_block = _build_general_from_orm(obj) if hasattr(obj, "category_id") else None
        details_block = _build_details_from_orm(obj) if hasattr(obj, "category_id") else None
        # Features: value slots from properties_normalized.more_features only; amenities from obj.features
        mf_for_features = None
        if hasattr(obj, "category_id") and hasattr(obj, "more_features") and obj.more_features is not None:
            mf_for_features = obj.more_features
            if isinstance(mf_for_features, str):
                try:
                    mf_for_features = json.loads(mf_for_features)
                except Exception:
                    mf_for_features = None
            if not isinstance(mf_for_features, dict):
                mf_for_features = None
        features_structured = (
            _build_structured_features(obj, mf_for_features)
            if hasattr(obj, "category_id")
            else None
        )
        pricing_block = _build_pricing_from_orm(obj) if hasattr(obj, "category_id") else None
        listing_type_value = pricing_block.listing_type if pricing_block else None
        media_block = _build_media_from_orm(obj) if hasattr(obj, "category_id") else None

        # Nested location for detail (same as list)
        location_detail = None
        if hasattr(obj, 'city_id') and (obj.city or obj.area_rel or obj.location_name or (obj.latitude and obj.longitude)):
            lat = float(obj.latitude) if obj.latitude is not None else None
            lng = float(obj.longitude) if obj.longitude is not None else None
            address_by_lang = get_address_all_languages(obj)
            location_detail = PropertyLocationDetail(
                country_id=1,
                country="Jordan",
                city_id=getattr(obj, 'city_id', None),
                city=obj.city.name if obj.city else None,
                region_id=getattr(obj, 'location_id', None),
                region=obj.area_rel.name if obj.area_rel else None,
                address=address_by_lang,
                latitude=lat,
                longitude=lng,
                map_embed_url=f"https://maps.google.com/?q={lat},{lng}" if (lat is not None and lng is not None) else None,
            )
        elif obj.latitude is not None and obj.longitude is not None:
            lat = float(obj.latitude)
            lng = float(obj.longitude)
            address_by_lang = get_address_all_languages(obj)
            location_detail = PropertyLocationDetail(
                country_id=1,
                country="Jordan",
                address=address_by_lang,
                latitude=lat,
                longitude=lng,
                map_embed_url=f"https://maps.google.com/?q={lat},{lng}",
            )
        
        return cls(
            id=prop_id,
            reference_number=getattr(obj, "reference_number", None),
            url=obj.url,
            title=title_by_lang,
            description=description_by_lang,
            category=category_name,
            property_type=property_type_name,
            status=status_name,
            listing_type=listing_type_value,
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
            more_features=None if hasattr(obj, "category_id") else more_features_list,
            media=media_block,
            latitude=float(obj.latitude) if obj.latitude is not None else None,
            longitude=float(obj.longitude) if obj.longitude is not None else None,
            location_name=obj.location_name,
            is_exclusive=getattr(obj, "is_exclusive", None),
            location=location_detail,
            location_detail=location_detail,
            general=general_block,
            details=details_block,
            features=features_structured,
            pricing=pricing_block,
            created_at=getattr(obj, "created_at", None),
            updated_at=getattr(obj, "updated_at", None),
            published_at=getattr(obj, "published_at", None),
            expires_at=getattr(obj, "expires_at", None),
            sold_at=getattr(obj, "sold_at", None),
            rented_at=getattr(obj, "rented_at", None),
            agent=get_mock_agent(),
            owner=get_mock_owner(),
            created_by=get_mock_created_by(),
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
