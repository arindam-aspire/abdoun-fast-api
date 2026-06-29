from __future__ import annotations

from app.models.live_schema import PropertyCategory, PropertyType


DCO_PROPERTY_TAXONOMY: tuple[dict[str, object], ...] = (
    {
        "slug": "residential",
        "name": "Residential",
        "types": (
            ("apartments", "Apartments"),
            ("villas", "Villas"),
            ("buildings", "Buildings"),
            ("farms", "Farms"),
        ),
    },
    {
        "slug": "commercial",
        "name": "Commercial",
        "types": (
            ("offices", "Offices"),
            ("showrooms", "Showrooms"),
            ("buildings", "Buildings"),
            ("warehouse", "Warehouse"),
            ("businesses", "Businesses"),
            ("villas", "Villas"),
        ),
    },
    {
        "slug": "land",
        "name": "Land",
        "types": (
            ("residential-lands", "Residential Lands"),
            ("commercial-lands", "Commercial Lands"),
            ("industrial-lands", "Industrial Lands"),
            ("agricultural-lands", "Agricultural Lands"),
            ("mixed-use-lands", "Mixed Use Lands"),
        ),
    },
)

CATEGORY_ORDER = {str(item["slug"]): index for index, item in enumerate(DCO_PROPERTY_TAXONOMY)}
TYPE_ORDER = {
    str(category["slug"]): {slug: index for index, (slug, _) in enumerate(category["types"])}
    for category in DCO_PROPERTY_TAXONOMY
}


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
