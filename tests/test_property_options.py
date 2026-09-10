from __future__ import annotations

from types import SimpleNamespace

from app.services.property_options import normalize_group_key, serialize_option


def test_normalize_group_key_accepts_camel_case_master_api_filters() -> None:
    assert normalize_group_key("furnishingStatus") == "furnishing_status"
    assert normalize_group_key("furnishing-status") == "furnishing_status"
    assert normalize_group_key("FLOOR") == "floor"
    assert normalize_group_key("listingPurpose") == "listing_purpose"


def test_serialize_option_returns_master_table_fields() -> None:
    option = SimpleNamespace(
        id=21,
        group_key="furnishing_status",
        name="Furnished",
        slug="furnished",
        numeric_value=None,
        display_order=0,
        is_active=True,
    )
    assert serialize_option(option) == {
        "id": 21,
        "group": "furnishing_status",
        "name": "Furnished",
        "slug": "furnished",
        "numeric_value": None,
        "display_order": 0,
        "is_active": True,
    }
