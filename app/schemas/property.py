"""Pydantic schemas for property search, detail, list, geo search, and structured blocks (location, pricing, media)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional
import json
import hashlib

from pydantic import BaseModel, Field, model_serializer

import uuid
from app.models.property_normalized import PropertyNormalized as Property
from app.utils.constants import Defaults, PropertyListingType
from app.services.translation_service import (
    get_title_description_for_language,
    get_title_description_all_languages,
    get_address_all_languages,
)

# Feature keys from CSV more_features that carry a value (appear in structured slots, not in amenities)
FEATURE_KEY_FINISHING = "Finishing"
FEATURE_KEY_WINDOWS = "Windows"
FEATURE_KEY_WINDOW_SHUTTERS = "Window Shutters"
FEATURE_KEY_DOORS = "Doors"
FEATURE_KEY_AIR_CONDITIONING = "Air Conditioning"
FEATURE_KEY_HEATING_SYSTEM = "Heating System"
FEATURE_KEY_HEATING_FUEL = "Heating Fuel"

FEATURE_VALUE_KEYS = {
    FEATURE_KEY_FINISHING,
    FEATURE_KEY_WINDOWS,
    FEATURE_KEY_WINDOW_SHUTTERS,
    FEATURE_KEY_DOORS,
    FEATURE_KEY_AIR_CONDITIONING,
    FEATURE_KEY_HEATING_SYSTEM,
    FEATURE_KEY_HEATING_FUEL,
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
    country_id: Optional[int] = Defaults.DEFAULT_COUNTRY_ID
    country: Optional[str] = Defaults.DEFAULT_COUNTRY
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
        return PropertyListingType.SALE_RENT
    if has_selling:
        return PropertyListingType.SALE
    if has_rent:
        return PropertyListingType.RENT
    return PropertyListingType.RENT  # default when no price


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


def _media_item_from_row(media_row: Any, idx: int) -> Optional[PropertyMediaItem]:
    item = PropertyMediaItem(
        id=int(getattr(media_row, "id", idx) or idx),
        url=str(getattr(media_row, "url", "") or ""),
        thumb_url=(getattr(media_row, "thumb_url", None) or getattr(media_row, "url", None)),
        is_primary=bool(getattr(media_row, "is_primary", False)),
        order=int(getattr(media_row, "display_order", idx) or idx),
        caption=getattr(media_row, "caption", None),
    )
    return item if item.url else None


def _append_media_item_by_type(
    item: PropertyMediaItem,
    media_type: str,
    images: list[PropertyMediaItem],
    videos: list[PropertyMediaItem],
    floor_plans: list[PropertyMediaItem],
    documents: list[PropertyMediaItem],
) -> None:
    if media_type == "video":
        videos.append(item)
    elif media_type == "floor_plan":
        floor_plans.append(item)
    elif media_type == "document":
        documents.append(item)
    else:
        images.append(item)


def _resolve_thumbnail(images: list[PropertyMediaItem]) -> Optional[str]:
    primary_image = next((img for img in images if img.is_primary), None)
    if primary_image:
        return primary_image.thumb_url or primary_image.url
    if images:
        return images[0].thumb_url or images[0].url
    return None


def _build_media_from_loaded_rows(
    media_rows: list[Any],
    images: list[PropertyMediaItem],
    videos: list[PropertyMediaItem],
    floor_plans: list[PropertyMediaItem],
    documents: list[PropertyMediaItem],
) -> Optional[str]:
    media_rows.sort(key=lambda m: (getattr(m, "display_order", 0) or 0, getattr(m, "id", 0) or 0))
    for idx, media_row in enumerate(media_rows, start=1):
        item = _media_item_from_row(media_row, idx)
        if not item:
            continue
        media_type = (getattr(media_row, "media_type", "image") or "image").strip().lower()
        _append_media_item_by_type(item, media_type, images, videos, floor_plans, documents)
    return _resolve_thumbnail(images)


def _build_media_from_legacy_images(obj: Property, images: list[PropertyMediaItem]) -> Optional[str]:
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
    return _resolve_thumbnail(images)


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
        thumbnail = _build_media_from_loaded_rows(media_rows, images, videos, floor_plans, documents)
    else:
        # Backward-compatible fallback while old images column still exists.
        thumbnail = _build_media_from_legacy_images(obj, images)

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
        or Defaults.DEFAULT_CURRENCY
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


def _get_normalized_feature_value(more_features: dict[str, Any], key: str) -> Optional[str]:
    value = more_features.get(key)
    if value is None:
        return None
    return _normalize_feature_value(str(value))


def _is_excluded_feature_name(name: str) -> bool:
    return name in FEATURE_VALUE_KEYS or name in META_FEATURE_NAMES or name in FEATURE_VALUE_LIKE_NAMES


def _is_view_amenity(amenity_slug: str, view_type: list[str]) -> bool:
    if "view" not in amenity_slug:
        return False
    if amenity_slug not in view_type:
        view_type.append(amenity_slug)
    return True


def _collect_amenities_and_views(features: list[Any]) -> tuple[list[str], Optional[bool], list[str]]:
    amenities: list[str] = []
    has_view: Optional[bool] = None
    view_type: list[str] = []

    for pf in features:
        feature = getattr(pf, "feature", None)
        if not feature:
            continue

        name = getattr(feature, "name", None) or ""
        if _is_excluded_feature_name(name):
            continue

        amenity_slug = _normalize_amenity_slug(name, getattr(feature, "slug", None))
        if not amenity_slug:
            continue

        if amenity_slug not in amenities:
            amenities.append(amenity_slug)
        if _is_view_amenity(amenity_slug, view_type):
            has_view = True

    return amenities, has_view, view_type


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

    mf = more_features or {}

    # Value slots: single source = more_features JSON (from DB column)
    finishing = _get_normalized_feature_value(mf, FEATURE_KEY_FINISHING)
    windows = _get_normalized_feature_value(mf, FEATURE_KEY_WINDOWS)
    window_shutters = _get_normalized_feature_value(mf, FEATURE_KEY_WINDOW_SHUTTERS)
    doors = _get_normalized_feature_value(mf, FEATURE_KEY_DOORS)
    air_conditioning = _get_normalized_feature_value(mf, FEATURE_KEY_AIR_CONDITIONING)
    heating_system = _get_normalized_feature_value(mf, FEATURE_KEY_HEATING_SYSTEM)
    heating_fuel = _get_normalized_feature_value(mf, FEATURE_KEY_HEATING_FUEL)

    amenities, has_view, view_type = _collect_amenities_and_views(obj.features or [])

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

    @staticmethod
    def _parse_normalized_images(raw_images: Any) -> list[Any]:
        if not raw_images:
            return []
        if isinstance(raw_images, str):
            try:
                parsed = json.loads(raw_images)
            except (TypeError, ValueError):
                return []
            return parsed if isinstance(parsed, list) else []
        return raw_images if isinstance(raw_images, list) else []

    @staticmethod
    def _coerce_prop_id(raw_id: Any) -> Any:
        if isinstance(raw_id, uuid.UUID):
            return uuid_to_int_hash(raw_id)
        if hasattr(raw_id, "__int__"):
            return int(raw_id)
        return raw_id

    @staticmethod
    def _extract_search_values(obj: Property) -> tuple[Any, Any, Any, Any]:
        price = obj.selling_price_amount or obj.rent_price_amount
        currency = obj.selling_price_currency or obj.rent_price_currency
        if hasattr(obj, "category_id"):
            images = PropertySearchResult._parse_normalized_images(obj.images)
            thumbnail = images[0] if images else None
            prop_id = PropertySearchResult._coerce_prop_id(obj.id)
        else:
            thumbnail = (obj.images or [None])[0]
            prop_id = obj.id
        return price, currency, thumbnail, prop_id

    @staticmethod
    def _sanitize_title(raw_title: Any) -> str:
        if raw_title and str(raw_title).lower() not in ("nan", "none"):
            return raw_title
        return Defaults.UNTITLED_PROPERTY

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
        price, currency, thumbnail, prop_id = cls._extract_search_values(obj)
        title = cls._sanitize_title(obj.title)
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


def _is_normalized_property(obj: Property) -> bool:
    return hasattr(obj, "category_id")


def _extract_city_area(obj: Property) -> tuple[Optional[str], Optional[str]]:
    city = None
    area_name = None
    if _is_normalized_property(obj):
        city = obj.city.name if obj.city else None
        area_name = obj.area_rel.name if obj.area_rel else None
    if (not city or not area_name) and obj.location_name:
        parts = obj.location_name.split(" - ")
        if len(parts) >= 2:
            area_name = area_name or parts[0].strip()
            city = city or parts[-1].strip()
        elif len(parts) == 1:
            city = city or parts[0].strip()
    return city, area_name


def _derive_status(has_selling_price: bool, has_rent_price: bool) -> Optional[str]:
    """Return listing status for display: buy or rent."""
    from app.utils.constants import ListingStatus
    if has_selling_price:
        return ListingStatus.BUY
    if has_rent_price:
        return ListingStatus.RENT
    return None


def _format_price_string(amount: Any, currency: Optional[str]) -> Optional[str]:
    if amount is None:
        return None
    price_val = float(amount)
    code = currency or Defaults.DEFAULT_CURRENCY_DISPLAY
    if price_val == int(price_val):
        return f"{int(price_val):,} {code}"
    return f"{price_val:,.2f} {code}"


def _format_area_string(value: Any) -> Optional[str]:
    if not value:
        return None
    area_val = float(value)
    if area_val == int(area_val):
        return f"{int(area_val):,}"
    return f"{area_val:,.2f}"


def _extract_category_context(obj: Property) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str], str]:
    if _is_normalized_property(obj):
        category_name = obj.category.name if obj.category else None
        type_name = obj.type.name if obj.type else None
        city_name = obj.city.name if obj.city else None
        area_name = obj.area_rel.name if obj.area_rel else None
    else:
        category_name = getattr(obj, "category", None)
        type_name = None
        city_name = None
        area_name = None
    return category_name, type_name, city_name, area_name, (category_name or "").lower()


def _resolve_land_search_type(category_lower: str) -> str:
    if "commercial" in category_lower:
        return "Commercial Lands"
    if "industrial" in category_lower:
        return "Industrial Lands"
    if "agricultural" in category_lower:
        return "Agricultural Lands"
    if "mixed" in category_lower or "use" in category_lower:
        return "Mixed-Use Lands"
    return "Residential Lands"


def _map_search_types(
    category_lower: str,
    category_name: Optional[str],
    type_name: Optional[str],
    is_normalized: bool,
) -> tuple[str, str, str]:
    mappings: list[tuple[bool, tuple[str, str, str]]] = [
        ("apartment" in category_lower, ("Apartments", "Apartment", "residential")),
        ("villa" in category_lower or "house" in category_lower, ("Villas", "Villa", "residential")),
        ("building" in category_lower and "land" not in category_lower, ("Buildings", "Building", "residential")),
        ("farm" in category_lower, ("Farms", "Farm", "residential")),
        ("office" in category_lower, ("Offices", "Office", "commercial")),
        ("showroom" in category_lower, ("Showrooms", "Showroom", "commercial")),
        ("warehouse" in category_lower, ("Warehouses", "Warehouse", "commercial")),
        ("business" in category_lower, ("Businesses", "Business", "commercial")),
    ]
    for condition, result in mappings:
        if condition:
            return result

    if "land" in category_lower:
        return _resolve_land_search_type(category_lower), "Lot / Land for sale", "land"

    if is_normalized and type_name:
        search_type = type_name if type_name.endswith("s") else f"{type_name}s"
        return search_type, type_name, "residential"
    if category_name:
        return category_name, category_name, "residential"
    return "Properties", "Property", "residential"


def _build_highlights(obj: Property, category_for_highlights: Optional[str]) -> Optional[str]:
    highlights_parts: list[str] = []
    if obj.bedrooms:
        highlights_parts.append(f"{obj.bedrooms}BHK")
    if category_for_highlights:
        highlights_parts.append(category_for_highlights)
    return " | ".join(highlights_parts) if highlights_parts else None


def _build_badges(has_selling_price: bool, has_rent_price: bool, is_verified: bool) -> Optional[list[str]]:
    badges: list[str] = []
    if has_selling_price:
        badges.append("For Sale")
    if has_rent_price:
        badges.append("For Rent")
    if is_verified:
        badges.append("Verified")
    return badges if badges else None


def _format_validated_date(created_at: Optional[datetime]) -> Optional[str]:
    if not created_at:
        return None
    day = created_at.day
    suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix} of {created_at.strftime('%B')}"


def _coerce_property_id(obj: Property) -> Any:
    if _is_normalized_property(obj):
        if isinstance(obj.id, uuid.UUID):
            return uuid_to_int_hash(obj.id)
        if hasattr(obj.id, "__int__"):
            return int(obj.id)
    return obj.id


def _map_embed_url(lat: Optional[float], lng: Optional[float]) -> Optional[str]:
    if lat is None or lng is None:
        return None
    return Defaults.MAP_EMBED_URL_TEMPLATE.format(lat=lat, lng=lng)


def _build_location_detail(obj: Property) -> Optional[PropertyLocationDetail]:
    is_normalized = _is_normalized_property(obj)
    has_geo = obj.latitude is not None and obj.longitude is not None
    has_rel = is_normalized and (obj.city or obj.area_rel or obj.location_name or has_geo)
    if not has_rel and not has_geo:
        return None

    lat = float(obj.latitude) if obj.latitude is not None else None
    lng = float(obj.longitude) if obj.longitude is not None else None
    address_by_lang = get_address_all_languages(obj)
    map_embed_url = _map_embed_url(lat, lng)

    if is_normalized:
        return PropertyLocationDetail(
            country_id=Defaults.DEFAULT_COUNTRY_ID,
            country=Defaults.DEFAULT_COUNTRY,
            city_id=getattr(obj, "city_id", None),
            city=obj.city.name if obj.city else None,
            region_id=getattr(obj, "location_id", None),
            region=obj.area_rel.name if obj.area_rel else None,
            address=address_by_lang,
            latitude=lat,
            longitude=lng,
            map_embed_url=map_embed_url,
        )

    return PropertyLocationDetail(
        country_id=Defaults.DEFAULT_COUNTRY_ID,
        country=Defaults.DEFAULT_COUNTRY,
        address=address_by_lang,
        latitude=lat,
        longitude=lng,
        map_embed_url=map_embed_url,
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
        city, area_name = _extract_city_area(obj)
        has_selling_price = obj.selling_price_amount is not None
        has_rent_price = obj.rent_price_amount is not None
        status = _derive_status(has_selling_price, has_rent_price)
        price_str = _format_price_string(
            obj.selling_price_amount if obj.selling_price_amount is not None else obj.rent_price_amount,
            obj.selling_price_currency if obj.selling_price_amount is not None else obj.rent_price_currency,
        )

        built_up_area = getattr(obj, "built_up_area", None) or getattr(obj, "area", None)
        area_str = _format_area_string(built_up_area)

        category_name, type_name, city_name, area_name_rel, category_lower = _extract_category_context(obj)
        if _is_normalized_property(obj):
            city = city_name or city
            area_name = area_name_rel or area_name
        search_property_type, property_type, category = _map_search_types(
            category_lower, category_name, type_name, _is_normalized_property(obj)
        )

        category_for_highlights = category_name if _is_normalized_property(obj) else getattr(obj, "category", None)
        highlights = _build_highlights(obj, category_for_highlights)

        is_verified = bool(getattr(obj, "is_verified", False))
        if not _is_normalized_property(obj):
            status_raw = getattr(obj, "status", None)
            is_verified = bool(status_raw and str(status_raw).lower() == "ok")
        badges = _build_badges(has_selling_price, has_rent_price, is_verified)

        title_by_lang, description_by_lang = get_title_description_all_languages(obj)
        validated_date_str = _format_validated_date(getattr(obj, "created_at", None))
        media_block = _build_media_from_orm(obj)
        prop_id = _coerce_property_id(obj)
        location_detail = _build_location_detail(obj)
        
        return cls(
            id=prop_id,
            reference_number=getattr(obj, "reference_number", None),
            title=title_by_lang,
            description=description_by_lang,
            price=price_str,
            status=status,
            category=category,
            searchPropertyType=search_property_type,
            city=city,
            areaName=area_name,
            propertyType=property_type,
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
            brokerName=Defaults.DEFAULT_BROKER_NAME,
            brokerLogo=None,  # Not available in current data model
            is_exclusive=getattr(obj, "is_exclusive", None),
            location_detail=location_detail,
        )


def _extract_detail_base_fields(
    obj: Property,
) -> tuple[bool, Optional[str], Optional[str], Optional[str], Any, Optional[float], Optional[Any]]:
    is_normalized = _is_normalized_property(obj)
    if is_normalized:
        category_name = obj.category.name if obj.category else None
        property_type_name = obj.type.name if obj.type else None
        status_name = obj.property_status.name if obj.property_status else None
        prop_id = _coerce_property_id(obj)
        built_up_area = float(obj.area) if obj.area is not None else None
        legacy_more_features = None
    else:
        category_name = getattr(obj, "category", None)
        property_type_name = getattr(obj, "property_type", None) or getattr(obj, "type", None)
        status_name = getattr(obj, "status", None)
        prop_id = obj.id
        built_up_area = float(obj.built_up_area) if obj.built_up_area is not None else None
        legacy_more_features = obj.more_features or []
    return is_normalized, category_name, property_type_name, status_name, prop_id, built_up_area, legacy_more_features


def _parse_more_features_for_structured(
    obj: Property, is_normalized: bool
) -> Optional[dict[str, Any]]:
    if not is_normalized or not hasattr(obj, "more_features") or obj.more_features is None:
        return None
    mf = obj.more_features
    if isinstance(mf, str):
        try:
            mf = json.loads(mf)
        except (TypeError, ValueError):
            return None
    return mf if isinstance(mf, dict) else None


def _build_detail_structured_blocks(
    obj: Property,
    is_normalized: bool,
    parsed_more_features: Optional[dict[str, Any]],
) -> tuple[
    Optional[PropertyGeneralStructured],
    Optional[PropertyDetailsStructured],
    Optional[PropertyFeaturesStructured],
    Optional[PropertyPricingStructured],
    Optional[str],
    Optional[PropertyMediaStructured],
]:
    if not is_normalized:
        return None, None, None, None, None, None
    general_block = _build_general_from_orm(obj)
    details_block = _build_details_from_orm(obj)
    features_structured = _build_structured_features(obj, parsed_more_features)
    pricing_block = _build_pricing_from_orm(obj)
    listing_type_value = pricing_block.listing_type if pricing_block else None
    media_block = _build_media_from_orm(obj)
    return general_block, details_block, features_structured, pricing_block, listing_type_value, media_block


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

        (
            is_normalized,
            category_name,
            property_type_name,
            status_name,
            prop_id,
            built_up_area,
            more_features_list,
        ) = _extract_detail_base_fields(obj)

        parsed_more_features = _parse_more_features_for_structured(obj, is_normalized)
        (
            general_block,
            details_block,
            features_structured,
            pricing_block,
            listing_type_value,
            media_block,
        ) = _build_detail_structured_blocks(obj, is_normalized, parsed_more_features)
        location_detail = _build_location_detail(obj)
        
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
            more_features=None if is_normalized else more_features_list,
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


class PropertyListResponse(BaseModel):
    """
    Schema for property list API response.
    
    Standard response format for property listing endpoints,
    containing the list of properties and total count.
    
    Attributes:
        items: List of property search results
        total: Total number of properties in the result set
    """
    items: List[PropertySearchResult]
    total: int


class PropertyListResponseExtended(BaseModel):
    """
    Extended schema for property list API response with frontend format.
    
    Attributes:
        items: List of extended property search results
        total: Total number of properties in the result set
    """
    items: List[PropertySearchResultExtended]
    total: int


class PropertySearchParams(BaseModel):
    """
    Query parameters for property list/search endpoints (GET /properties, /properties/exclusive).
    """
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

    model_config = {"extra": "ignore"}


class PropertySearchResponse(BaseModel):
    """
    Search API response matching the exact frontend contract.
    
    Attributes:
        data: List of property search results
        total: Total number of properties matching filters
        page: Current page number (1-based)
        pageSize: Number of items per page
    """
    data: List[PropertySearchResultExtended]
    total: int
    page: int
    pageSize: int
