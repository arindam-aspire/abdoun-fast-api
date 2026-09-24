from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.property_options import normalize_group_key, resolve_property_option, serialize_option


def test_normalize_group_key_accepts_camel_case_master_api_filters() -> None:
    assert normalize_group_key("furnishingStatus") == "furnishing_status"
    assert normalize_group_key("furnishing-status") == "furnishing_status"
    assert normalize_group_key("FLOOR") == "floor"
    assert normalize_group_key("listingPurpose") == "listing_purpose"
    assert normalize_group_key("landType") == "land_type"
    assert normalize_group_key("land-type") == "land_type"


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


def test_under_construction_completion_status_is_rejected() -> None:
    with pytest.raises(HTTPException) as exc_info:
        resolve_property_option(
            MagicMock(),
            group="completion_status",
            value="Under Construction",
            field="property_details.completion_status",
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "INVALID_VALUE"
    assert "Under Construction" in exc_info.value.detail["message"]
