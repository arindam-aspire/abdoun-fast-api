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
    assert details["floorNumber"] == "1"
    assert details["floor_number"] == "1"
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


def _media_db_mock(existing: list | None = None) -> MagicMock:
    db = MagicMock()
    db.scalars.return_value.all.return_value = list(existing or [])
    return db


def test_media_sync_persists_exactly_one_primary_image() -> None:
    db = _media_db_mock()
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


def test_media_sync_accepts_file_url_aliases() -> None:
    db = _media_db_mock()
    sync_property_media_from_payload(
        db,
        property_id=uuid4(),
        payload={"media_documents": {"images": [{"fileUrl": "https://example.com/one.jpg"}]}},
    )
    added = db.add.call_args_list[0].args[0]
    assert added.url == "https://example.com/one.jpg"
    assert added.is_primary is True


def test_media_sync_does_not_mark_non_images_primary() -> None:
    db = _media_db_mock()
    sync_property_media_from_payload(
        db,
        property_id=uuid4(),
        payload={
            "media_documents": {
                "images": [{"url": "https://example.com/one.jpg", "isPrimary": True}],
                "youtube_url": "https://youtube.com/watch?v=abc",
                "floor_plan_images": [{"url": "https://example.com/plan.jpg"}],
                "documents": [{"url": "https://example.com/doc.pdf"}],
            }
        },
    )
    rows = [call.args[0] for call in db.add.call_args_list]
    assert sum(bool(row.is_primary) for row in rows) == 1
    assert all(row.is_primary for row in rows if row.media_type == "image")
    assert not any(row.is_primary for row in rows if row.media_type != "image")


def test_media_sync_flushes_existing_primary_before_insert() -> None:
    existing = SimpleNamespace(is_primary=True, media_type="image")
    db = _media_db_mock([existing])
    sync_property_media_from_payload(
        db,
        property_id=uuid4(),
        payload={"media_documents": {"images": [{"url": "https://example.com/one.jpg"}]}},
    )
    method_names = [name for name, *_ in db.method_calls]
    assert method_names.index("flush") < method_names.index("add")
    assert db.delete.call_args_list[0].args[0] is existing
    assert db.flush.call_count >= 2


def test_exact_plot_and_hod_match_is_a_duplicate_property() -> None:
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = uuid4()
    with pytest.raises(HTTPException) as exc_info:
        validate_duplicate_property(
            db,
            {"property_details": {"plot_number": "12", "hod_code": "B-3"}},
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
                "plot_number": "88",
            },
            "property_details": {"bedrooms": 2},
        },
    )
    location = payload["location"]
    details = payload["property_details"]
    assert location["gov_code"] == "1"
    assert location["gov_name"] == "Capital"
    assert location["vill_code"] == "101"
    assert location["hod_code"] == "H-9"
    assert location["parcel_number"] == "44"
    assert location["plot_number"] == "88"
    assert "basin_number" not in location
    assert "government_code" not in location
    assert details["gov_code"] == "1"
    assert details["vill_code"] == "101"
    assert details["hod_code"] == "H-9"
    assert details["parcel_number"] == "44"
    assert details["plot_number"] == "88"
    assert "basin_number" not in details
    assert "government_code" not in details


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


def test_parking_spaces_accepts_manual_numeric_and_legacy_dropdown_values() -> None:
    numeric = prepare_property_payload(
        MagicMock(),
        {"property_details": {"parkingSpace": "2", "built_up_area": 100}},
    )
    legacy = prepare_property_payload(
        MagicMock(),
        {"property_details": {"parking": {"name": "Available", "id": 44}, "built_up_area": 100}},
    )
    zero = prepare_property_payload(
        MagicMock(),
        {"property_details": {"parking_spaces": 0, "built_up_area": 100}},
    )

    assert numeric["property_details"]["parking_spaces"] == 2
    assert numeric["property_details"]["parking"] == 2
    assert legacy["property_details"]["parking_spaces"] == 1
    assert zero["property_details"]["parking_spaces"] == 0


def test_invalid_parking_spaces_are_rejected() -> None:
    with pytest.raises(HTTPException) as exc_info:
        prepare_property_payload(MagicMock(), {"property_details": {"parking_spaces": "underground"}})

    assert exc_info.value.detail["code"] == "VALIDATION_ERROR"
    assert exc_info.value.detail["details"][0]["field"] == "property_details.parking_spaces"


def test_parking_option_id_alone_is_not_treated_as_space_count() -> None:
    with pytest.raises(HTTPException) as exc_info:
        prepare_property_payload(MagicMock(), {"property_details": {"parking": {"id": 44}}})

    assert exc_info.value.detail["details"][0]["field"] == "property_details.parking_spaces"


def test_step3_payload_with_parking_and_parcel_ids_can_continue_to_step4(monkeypatch) -> None:
    monkeypatch.setattr("app.services.property_submissions._is_mock_session", lambda _db: False)
    monkeypatch.setattr("app.services.property_submissions.dls_official_name", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.services.property_submissions.resolve_property_option",
        lambda _db, *, group, value, field: _option(group, value),
    )

    payload = prepare_property_payload(
        MagicMock(),
        {
            "location": {"city_id": 1, "area_id": 2},
            "property_details": {
                "built_up_area": 140,
                "bedrooms": 3,
                "bathrooms": 2,
                "parking_spaces": 2,
                "plot_number": "12",
                "basin_number": "B-3",
                "year_built": "",
                "furnishing_status": "Furnished",
                "floor_level": "First",
            },
        },
    )
    details = payload["property_details"]
    assert details["parking_spaces"] == 2
    assert details["plot_number"] == "12"
    assert "basin_number" not in details
    assert not details.get("hod_code")
    assert details.get("year_built") in (None, "")
    assert details["furnishing_status"] == "furnished"


def test_unknown_dls_hod_with_parent_path_is_still_rejected(monkeypatch) -> None:
    monkeypatch.setattr("app.services.property_submissions._is_mock_session", lambda _db: False)

    def _official_name(_db, *, level: str, code: str, parents: dict | None = None):
        if level == "hod":
            return None
        return f"Official-{level}-{code}"

    monkeypatch.setattr("app.services.property_submissions.dls_official_name", _official_name)

    with pytest.raises(HTTPException) as exc_info:
        prepare_property_payload(
            MagicMock(),
            {
                "location": {
                    "gov_code": "1",
                    "dept_code": "11",
                    "vill_code": "101",
                    "hod_code": "NOT-A-CODE",
                }
            },
        )

    assert exc_info.value.detail["details"][0]["field"] == "location.hod_code"


def test_residential_identification_fields_are_optional_and_persisted(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.property_submissions.resolve_property_option",
        lambda _db, *, group, value, field: _option(group, value),
    )
    payload = prepare_property_payload(
        MagicMock(),
        {
            "basic_information": {"category_slug": "residential"},
            "location": {
                "apartmentNumber": "12A",
                "plot_number": "88",
                "basin_number": "B-1",
                "parcel_number": "P-9",
                "building": "14",
            },
            "property_details": {"floor_level": "First", "bedrooms": 2},
        },
    )
    location = payload["location"]
    details = payload["property_details"]
    assert location["apartment_number"] == "12A"
    assert location["plot_number"] == "88"
    assert "basin_number" not in location
    assert location["parcel_number"] == "P-9"
    assert location["building_number"] == "14"
    assert location["building"] == "14"
    assert details["apartment_number"] == "12A"
    assert details["building_number"] == "14"
    assert details["parcel_number"] == "P-9"
    assert details["floor_number"] == "1"


def test_land_identification_fields_are_ignored() -> None:
    payload = prepare_property_payload(
        MagicMock(),
        {
            "basic_information": {"category_slug": "land", "category": "land"},
            "location": {
                "gov_code": "1",
                "gov_name": "Capital",
                "dept_code": "11",
                "vill_code": "101",
                "hod_code": "H-1",
                "sect_code": "0",
                "plot_number": "220",
                "parcel_number": "P-should-drop",
                "building": "Tower-1",
                "apartment_number": "A-4",
                "basin_number": "B-9",
            },
            "property_details": {
                "landType": "residential-lands",
                "landTypeId": 99,
                "floor_number": "2",
            },
        },
    )
    location = payload["location"]
    details = payload["property_details"]
    assert location["gov_code"] == "1"
    assert location["dept_code"] == "11"
    assert location["vill_code"] == "101"
    assert location["hod_code"] == "H-1"
    assert location["sect_code"] == "0"
    assert location["plot_number"] == "220"
    assert details["plot_number"] == "220"
    assert "land_type" not in details
    assert "land_type" not in location
    assert "land_type_id" not in details
    assert "landTypeId" not in details
    assert "parcel_number" not in details
    assert "parcel_number" not in location
    assert "building_number" not in details
    assert "building" not in details
    assert "apartment_number" not in details
    assert "floor_number" not in details
    assert "floor" not in details
    assert "basin_number" not in details
    assert "basin_number" not in location


def test_residential_land_type_is_normalized_from_master_data(monkeypatch) -> None:
    option = MagicMock()
    option.id = 401
    option.slug = "building-offices"
    option.name = "بناء/مكاتب"
    option.numeric_value = None

    def _resolve(_db, *, group, value, field):
        assert group == "land_type"
        assert value in {401, "بناء/مكاتب", "building-offices"}
        return option

    monkeypatch.setattr("app.services.property_submissions.resolve_property_option", _resolve)
    payload = prepare_property_payload(
        MagicMock(),
        {
            "basic_information": {"category_slug": "residential", "category": "residential"},
            "property_details": {"landTypeId": 401},
        },
    )
    details = payload["property_details"]
    assert details["land_type"] == "building-offices"
    assert details["landType"] == "building-offices"
    assert details["land_type_id"] == 401
    assert details["landTypeId"] == 401
    assert details["land_type_name"] == "بناء/مكاتب"
    assert details["landTypeName"] == "بناء/مكاتب"


def test_residential_friendly_dls_aliases_normalize_to_canonical_keys() -> None:
    payload = prepare_property_payload(
        MagicMock(),
        {
            "basic_information": {"category_slug": "residential"},
            "location": {
                "governate": "Capital",
                "governate_code": "1",
                "directorate": "Dir-A",
                "directorate_code": "11",
                "village": "Vill-A",
                "village_code": "101",
                "parcel_name": "Hod-A",
                "parcel_name_code": "H-1",
                "section": "Sect-A",
                "section_code": "3",
                "apartment": "12A",
                "building": "14",
                "parcel_number": "P-9",
                "plot_number": "88",
            },
            "property_details": {},
        },
    )
    location = payload["location"]
    details = payload["property_details"]
    assert location["gov_code"] == "1"
    assert location["gov_name"] == "Capital"
    assert location["dept_code"] == "11"
    assert location["dept_name"] == "Dir-A"
    assert location["vill_code"] == "101"
    assert location["vill_name"] == "Vill-A"
    assert location["hod_code"] == "H-1"
    assert location["hod_name"] == "Hod-A"
    assert location["sect_code"] == "3"
    assert location["sect_name"] == "Sect-A"
    assert location["apartment_number"] == "12A"
    assert location["building_number"] == "14"
    assert location["building"] == "14"
    assert location["parcel_number"] == "P-9"
    assert location["plot_number"] == "88"
    assert "governate" not in location
    assert "parcel_name" not in location
    assert "apartment" not in location
    assert details["apartment_number"] == "12A"
    assert details["hod_code"] == "H-1"
    assert details["parcel_number"] == "P-9"


def test_commercial_dls_fields_match_residential_rules(monkeypatch) -> None:
    land_type = SimpleNamespace(id=401, slug="building-offices", name="بناء/مكاتب", numeric_value=None)

    def _resolve(_db, *, group, value, field):
        if group == "land_type":
            return land_type
        return _option(group, value)

    monkeypatch.setattr("app.services.property_submissions.resolve_property_option", _resolve)
    payload = prepare_property_payload(
        MagicMock(),
        {
            "basic_information": {"category_slug": "commercial", "category": "commercial"},
            "location": {
                "gov_code": "1",
                "dept_code": "11",
                "vill_code": "101",
                "hod_code": "H-2",
                "sect_code": "0",
                "parcel_number": "C-1",
                "plot_number": "9",
                "building": "B1",
                "apartment": "A1",
            },
            "property_details": {"landTypeId": 401, "floor": "First"},
        },
    )
    location = payload["location"]
    details = payload["property_details"]
    assert location["gov_code"] == "1"
    assert location["hod_code"] == "H-2"
    assert location["parcel_number"] == "C-1"
    assert location["building_number"] == "B1"
    assert location["apartment_number"] == "A1"
    assert details["land_type_id"] == 401
    assert details["floor_number"] == "1"
    assert details["plot_number"] == "9"

