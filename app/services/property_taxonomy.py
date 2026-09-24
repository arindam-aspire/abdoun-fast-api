from __future__ import annotations

import re
from typing import Any

from app.core.app_defaults import get_property_taxonomy
from app.models.live_schema import PropertyCategory, PropertyType


DCO_PROPERTY_TAXONOMY = tuple(get_property_taxonomy())
CATEGORY_ORDER = {str(item["slug"]): index for index, item in enumerate(DCO_PROPERTY_TAXONOMY)}
TYPE_ORDER = {
    str(category["slug"]): {slug: index for index, (slug, _) in enumerate(category["types"])}
    for category in DCO_PROPERTY_TAXONOMY
}
CATEGORY_GROUPS = {
    str(item["slug"]): {
        "group_slug": str(item.get("group_slug") or ("land" if item["slug"] == "land" else "properties")),
        "group_name": str(item.get("group_name") or ("Land" if item["slug"] == "land" else "Properties")),
    }
    for item in DCO_PROPERTY_TAXONOMY
}
GROUP_ORDER = (
    {"slug": "properties", "name": "Properties"},
    {"slug": "land", "name": "Land"},
)

# Category-dependent DLS / parcel identification fields (optional unless BRD requires).
IDENTIFICATION_FIELD_META: dict[str, dict[str, Any]] = {
    "land_type": {
        "key": "land_type",
        "label": "Land Type",
        "aliases": ("landType", "land_type", "land_type_id", "landTypeId"),
    },
    "floor_number": {
        "key": "floor_number",
        "label": "Floor Number",
        "aliases": ("floorNumber", "floor_number", "floor", "floor_level", "floorLevel", "floor_id", "floorId"),
    },
    "apartment_number": {
        "key": "apartment_number",
        "label": "Apartment Number",
        "aliases": ("apartmentNumber", "apartment_number", "apartment"),
    },
    "plot_number": {
        "key": "plot_number",
        "label": "Plot Number",
        "aliases": ("plotNumber", "plot_number"),
    },
    "parcel_number": {
        "key": "parcel_number",
        "label": "Parcel Number",
        "aliases": ("parcelNumber", "parcel_number"),
    },
    "building_number": {
        "key": "building_number",
        "label": "Building Number",
        "aliases": ("buildingNumber", "building_number", "building"),
    },
}

# Residential/Commercial share the same identification set.
# Land keeps only plot_number (plus DLS hierarchy codes outside this list).
_PROPERTIES_IDENTIFICATION_KEYS = (
    "land_type",
    "floor_number",
    "apartment_number",
    "plot_number",
    "parcel_number",
    "building_number",
)
_LAND_IDENTIFICATION_KEYS: tuple[str, ...] = ("plot_number",)
CATEGORY_IDENTIFICATION_FIELDS: dict[str, tuple[str, ...]] = {
    "residential": _PROPERTIES_IDENTIFICATION_KEYS,
    "commercial": _PROPERTIES_IDENTIFICATION_KEYS,
    "land": _LAND_IDENTIFICATION_KEYS,
}

# Land ignores these identification keys when present on request payloads.
LAND_IGNORED_IDENTIFICATION_KEYS = (
    "land_type",
    "landType",
    "land_type_id",
    "landTypeId",
    "land_type_name",
    "landTypeName",
    "parcel_number",
    "parcelNumber",
    "building",
    "building_number",
    "buildingNumber",
    "floor",
    "floor_number",
    "floorNumber",
    "floor_level",
    "floorLevel",
    "floor_id",
    "floorId",
    "apartment_number",
    "apartmentNumber",
    "apartment",
)

# Basin Number is retired for all categories.
RETIRED_IDENTIFICATION_KEYS = (
    "basin_number",
    "basinNumber",
)


def sort_categories(categories: list[PropertyCategory]) -> list[PropertyCategory]:
    return sorted(
        categories,
        key=lambda category: (
            CATEGORY_ORDER.get(category.slug, len(CATEGORY_ORDER)),
            category.name.casefold(),
        ),
    )


def sort_property_types(category_slug: str, property_types: list[PropertyType]) -> list[PropertyType]:
    type_order = TYPE_ORDER.get(category_slug, {})
    return sorted(
        property_types,
        key=lambda property_type: (
            type_order.get(property_type.slug, len(type_order)),
            property_type.name.casefold(),
        ),
    )


def is_dco_category(category: PropertyCategory) -> bool:
    return category.slug in CATEGORY_ORDER


def is_dco_property_type(category_slug: str, property_type: PropertyType) -> bool:
    return property_type.slug in TYPE_ORDER.get(category_slug, {})


def category_group(category: PropertyCategory | str) -> dict[str, str]:
    if isinstance(category, str):
        slug = category
        db_group_slug = None
        db_group_name = None
    else:
        # Duck-type ORM rows and test doubles that expose `.slug`.
        slug = str(getattr(category, "slug", "") or "")
        db_group_slug = getattr(category, "group_slug", None)
        db_group_name = getattr(category, "group_name", None)
    configured = CATEGORY_GROUPS.get(slug, {"group_slug": "properties", "group_name": "Properties"})
    return {
        "group_slug": str(db_group_slug or configured["group_slug"]),
        "group_name": str(db_group_name or configured["group_name"]),
    }


def serialize_category_group(category: PropertyCategory) -> dict[str, Any]:
    return category_group(category)


def _category_slug(category: PropertyCategory | str | None) -> str:
    if category is None:
        return ""
    if isinstance(category, str):
        return category.strip().casefold()
    return str(getattr(category, "slug", "") or "").strip().casefold()


def identification_field_keys(category: PropertyCategory | str | None) -> tuple[str, ...]:
    """Return canonical identification field keys applicable to the category."""
    slug = _category_slug(category)
    return CATEGORY_IDENTIFICATION_FIELDS.get(slug, _PROPERTIES_IDENTIFICATION_KEYS)


def is_identification_field_applicable(category: PropertyCategory | str | None, field_key: str) -> bool:
    return field_key in identification_field_keys(category)


def _alpha_initials(label: str | None, *, first_token_only: bool = False) -> str:
    """Build initials from a master-data name or slug (letters only)."""
    if not isinstance(label, str):
        return ""
    tokens = [token for token in re.split(r"[^A-Za-z0-9]+", label.strip()) if token]
    initials: list[str] = []
    for token in tokens:
        for character in token:
            if character.isalpha():
                initials.append(character.upper())
                break
        if first_token_only and initials:
            break
    return "".join(initials)


def reference_number_prefix_from_labels(category_label: str | None, type_label: str | None) -> str | None:
    """Prefix = category first letter + property-type word initials from master labels."""
    category_part = _alpha_initials(category_label, first_token_only=True)
    type_part = _alpha_initials(type_label, first_token_only=False)
    if category_part and type_part:
        return f"{category_part}{type_part}"
    return None


def taxonomy_labels_for_slugs(category_slug: str | None, type_slug: str | None) -> tuple[str | None, str | None]:
    """Resolve display names from property_taxonomy.json when DB rows are unavailable."""
    wanted_category = (category_slug or "").strip().casefold()
    wanted_type = (type_slug or "").strip().casefold()
    if not wanted_category:
        return None, None
    for item in DCO_PROPERTY_TAXONOMY:
        slug = str(item.get("slug") or "").strip().casefold()
        if slug != wanted_category:
            continue
        category_name = str(item.get("name") or item.get("slug") or "") or None
        type_name = None
        if wanted_type:
            for type_slug_value, type_name_value in item.get("types") or []:
                if str(type_slug_value).strip().casefold() == wanted_type:
                    type_name = str(type_name_value or type_slug_value)
                    break
        return category_name, type_name
    return None, None


def serialize_identification_fields(category: PropertyCategory | str | None) -> list[dict[str, Any]]:
    """API-facing list of optional identification fields for a category."""
    keys = identification_field_keys(category)
    fields: list[dict[str, Any]] = []
    for key in keys:
        meta = IDENTIFICATION_FIELD_META.get(key)
        if not meta:
            continue
        fields.append(
            {
                "key": meta["key"],
                "label": meta["label"],
                "required": False,
                "aliases": list(meta["aliases"]),
            }
        )
    return fields
