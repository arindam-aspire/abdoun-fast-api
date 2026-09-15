from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.property_submissions import (
    prepare_property_payload,
    remove_dld_number,
    sync_property_media_from_payload,
    validate_duplicate_property,
    validate_pricing,
)


def _option(group: str, value: object) -> SimpleNamespace:
    token = str(value).strip().lower().replace("_", "-").replace(" ", "-")
    aliases = {"sale-+-rent": "sale-or-rent", "first": "1", "semi-furnished": "semi-furnished"}
    token = aliases.get(token, token)
    ids = {
        "floor": 101,
        "furnishing_status": 201,
        "listing_purpose": 301,
        "completion_status": 401,
        "direction": 501,
    }
    return SimpleNamespace(
        id=ids.get(group, 1),
        slug=token,
        name=str(value),
        numeric_value=1 if group == "floor" else None,
    )


def test_property_payload_normalizes_master_data_aliases_and_reuses_existing_keys(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.property_submissions.resolve_property_option",
        lambda _db, *, group, value, field: _option(group, value),
    )
    payload = prepare_property_payload(
        MagicMock(),
        {
            "basic_information": {"listing_purpose": "Sale + Rent"},
            "location": {"map_pin": {"lat": 31.95, "lng": 35.91}},
            "property_details": {
                "property_area": 120,
                "furnishing_status": "Semi Furnished",
                "floor_level": "First",
                "completion_status": "Secondary",
                "direction": "Northeast",
                "year_of_construction": 2020,
                "dld_number": "retired",
            },
            "media_documents": {
                "images": [
                    {"url": "one.jpg", "is_primary": True},
                    {"url": "two.jpg", "is_primary": True},
                ]
            },
        },
    )

    assert payload["basic_information"]["listing_purpose"] == "sale_or_rent"
    assert payload["location"]["latitude"] == 31.95
    assert payload["location"]["longitude"] == 35.91
    assert "map_pin" not in payload["location"]
    details = payload["property_details"]
    assert details["built_up_area"] == 120
    assert details["furnishing"] == "semi-furnished"
    assert details["furnishing_status"] == "semi-furnished"
    assert details["furnishingStatus"] == "semi-furnished"
    assert details["furnishing_status_id"] == 201
    assert details["furnishingStatusId"] == 201
    assert details["floor"] == 1
    assert details["floor_id"] == 101
    assert details["floorNumber"] == 1
    assert details["floor_number"] == 1
    assert details["floor_level"] == "First"
    assert details["year_built"] == 2020
    assert "dld_number" not in details
    assert [image["is_primary"] for image in payload["media_documents"]["images"]] == [True, False]


def test_property_area_rejects_multi_select_values() -> None:
    with pytest.raises(HTTPException) as exc_info:
        prepare_property_payload(MagicMock(), {"property_details": {"built_up_area": [100, 120]}})

    assert exc_info.value.detail["code"] == "VALIDATION_ERROR"
    assert exc_info.value.detail["details"][0]["field"] == "property_details.built_up_area"


def test_submit_location_allows_missing_map_pin_coordinates() -> None:
    payload = prepare_property_payload(
        MagicMock(),
        {"location": {"city_id": 1, "area_id": 2}},
        for_submit=True,
    )

    assert payload["location"]["city_id"] == 1
    assert payload["location"]["area_id"] == 2
    assert payload["location"].get("latitude") is None
    assert payload["location"].get("longitude") is None
    assert "map_pin" not in payload["location"]


def test_submit_location_keeps_optional_map_pin_coordinates() -> None:
    payload = prepare_property_payload(
        MagicMock(),
        {"location": {"city_id": 1, "map_pin": {"lat": 31.95, "lng": 35.91}}},
        for_submit=True,
    )

    assert payload["location"]["latitude"] == 31.95
    assert payload["location"]["longitude"] == 35.91
    assert "map_pin" not in payload["location"]


def test_submit_location_treats_blank_or_partial_coordinates_as_absent() -> None:
    blank = prepare_property_payload(
        MagicMock(),
        {"location": {"latitude": "", "longitude": "  "}},
        for_submit=True,
    )
    partial = prepare_property_payload(
        MagicMock(),
        {"location": {"latitude": 31.95}},
        for_submit=True,
    )

    assert blank["location"]["latitude"] is None
    assert blank["location"]["longitude"] is None
    assert partial["location"]["latitude"] is None
    assert partial["location"]["longitude"] is None


def test_add_property_location_area_is_single_select() -> None:
    with pytest.raises(HTTPException) as exc_info:
        prepare_property_payload(MagicMock(), {"location": {"area_id": [1, 2]}})

    assert exc_info.value.detail["details"][0]["field"] == "location.area_id"


def test_sale_and_rent_requires_both_relevant_prices() -> None:
    payload = {
        "basic_information": {"listing_purpose": "sale_or_rent"},
        "property_details": {"furnishing": "furnished"},
        "pricing": {"furnished_sale_price": 100000, "currency": "JOD"},
    }
    with pytest.raises(HTTPException) as exc_info:
        validate_pricing(payload, for_submit=True)

    assert exc_info.value.detail["details"][0]["field"] == "pricing.furnished_rent_price"


def test_sale_and_rent_accepts_both_relevant_prices() -> None:
    validate_pricing(
        {
            "basic_information": {"listing_purpose": "sale_or_rent"},
            "property_details": {"furnishing": "semi-furnished"},
            "pricing": {
                "unfurnished_sale_price": 100000,
                "semi_furnished_rent_price": 700,
                "currency": "JOD",
            },
        },
        for_submit=True,
    )


def test_media_sync_persists_exactly_one_primary_image() -> None:
    db = MagicMock()
    sync_property_media_from_payload(
        db,
        property_id=uuid4(),
        payload={
            "media_documents": {
                "images": [
                    {"url": "https://example.com/one.jpg", "is_primary": True},
                    {"url": "https://example.com/two.jpg", "is_primary": True},
                ]
            }
        },
    )
    image_rows = [
        call.args[0]
        for call in db.add.call_args_list
        if call.args[0].media_type == "image"
    ]
    assert sum(bool(row.is_primary) for row in image_rows) == 1


def test_exact_plot_and_basin_match_is_a_duplicate_property() -> None:
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = uuid4()
    with pytest.raises(HTTPException) as exc_info:
        validate_duplicate_property(
            db,
            {"property_details": {"plot_number": "12", "basin_number": "B-3"}},
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "DUPLICATE_PROPERTY"


def test_retired_dld_number_is_not_returned() -> None:
    payload = remove_dld_number(
        {"property_details": {"dldNumber": "DLD-1", "apartment_number": "12A"}}
    )
    assert payload["property_details"] == {"apartment_number": "12A"}


def test_dls_parcel_fields_are_persisted_on_location_and_details() -> None:
    payload = prepare_property_payload(
        MagicMock(),
        {
            "location": {
                "GOV_CODE": "1",
                "GOV_NAME": "Capital",
                "DEPT_CODE": "11",
                "VILL_CODE": "101",
                "HOD_CODE": "H-9",
                "SECT_CODE": "3",
                "parcel_number": "44",
            },
            "property_details": {"bedrooms": 2},
        },
    )
    location = payload["location"]
    details = payload["property_details"]
    assert location["gov_code"] == "1"
    assert location["vill_code"] == "101"
    assert location["hod_code"] == "H-9"
    assert location["parcel_number"] == "44"
    assert location["plot_number"] == "44"
    assert details["gov_code"] == "1"
    assert details["vill_code"] == "101"
    assert details["hod_code"] == "H-9"
    assert details["parcel_number"] == "44"
    assert details["basin_number"] == "H-9"


def test_official_dls_parcel_identifiers_are_duplicates() -> None:
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = uuid4()
    with pytest.raises(HTTPException) as exc_info:
        validate_duplicate_property(
            db,
            {
                "location": {
                    "vill_code": "101",
                    "hod_code": "H-9",
                    "parcel_number": "44",
                }
            },
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "DUPLICATE_PROPERTY"


def test_sale_furnished_keeps_only_furnished_sale_price(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.property_submissions.resolve_property_option",
        lambda _db, *, group, value, field: _option(group, value),
    )
    payload = prepare_property_payload(
        MagicMock(),
        {
            "basic_information": {"listing_purpose": "sale"},
            "property_details": {"furnishing": "furnished"},
            "pricing": {
                "furnished_sale_price": 150000,
                "unfurnished_sale_price": 140000,
                "furnished_rent_price": 800,
                "currency": "JOD",
            },
        },
    )
    pricing = payload["pricing"]
    assert pricing["furnished_sale_price"] == 150000
    assert "unfurnished_sale_price" not in pricing
    assert "furnished_rent_price" not in pricing


def test_rent_semi_furnished_requires_matching_price() -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_pricing(
            {
                "basic_information": {"listing_purpose": "rent"},
                "property_details": {"furnishing": "semi-furnished"},
                "pricing": {"furnished_rent_price": 900, "currency": "JOD"},
            },
            for_submit=True,
        )
    assert exc_info.value.detail["details"][0]["field"] == "pricing.semi_furnished_rent_price"


def test_owner_id_or_passport_aliases_are_normalized() -> None:
    payload = prepare_property_payload(
        MagicMock(),
        {
            "owner_information": {
                "owners": [{"full_name": "Omar", "passport_number": "P-998877"}]
            }
        },
    )
    owner = payload["owner_information"]["owners"][0]
    assert owner["ssi"] == "P-998877"
    assert owner["owner_id_or_passport"] == "P-998877"
    assert owner["identification_number"] == "P-998877"
    assert owner["social_security_id"] == "P-998877"

