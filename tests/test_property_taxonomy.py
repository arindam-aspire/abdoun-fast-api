"""Property taxonomy grouping: Properties vs Land."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.api.v1.routes import public_catalog
from app.services.property_taxonomy import (
    GROUP_ORDER,
    category_group,
    identification_field_keys,
    serialize_identification_fields,
    sort_categories,
)


def test_category_groups_place_residential_and_commercial_under_properties() -> None:
    residential = category_group("residential")
    commercial = category_group("commercial")
    land = category_group("land")

    assert residential == {"group_slug": "properties", "group_name": "Properties"}
    assert commercial == {"group_slug": "properties", "group_name": "Properties"}
    assert land == {"group_slug": "land", "group_name": "Land"}
    assert [group["slug"] for group in GROUP_ORDER] == ["properties", "land"]


def test_identification_fields_are_category_dependent() -> None:
    residential_keys = identification_field_keys("residential")
    commercial_keys = identification_field_keys("commercial")
    land_keys = identification_field_keys("land")

    assert residential_keys == commercial_keys
    assert residential_keys == (
        "land_type",
        "floor_number",
        "apartment_number",
        "plot_number",
        "parcel_number",
        "building_number",
    )
    assert land_keys == ("plot_number",)
    assert "basin_number" not in residential_keys
    assert "land_type" in residential_keys
    assert "land_type" not in land_keys
    assert "plot_number" in land_keys
    assert "parcel_number" not in land_keys
    assert "building_number" not in land_keys
    assert "floor_number" not in land_keys
    assert "apartment_number" not in land_keys

    land_fields = serialize_identification_fields("land")
    assert land_fields == [
        {
            "key": "plot_number",
            "label": "Plot Number",
            "required": False,
            "aliases": ["plotNumber", "plot_number"],
        }
    ]


def test_property_taxonomy_response_groups_categories() -> None:
    residential = SimpleNamespace(id=1, name="Residential", slug="residential", group_slug=None, group_name=None)
    commercial = SimpleNamespace(id=2, name="Commercial", slug="commercial", group_slug=None, group_name=None)
    land = SimpleNamespace(id=3, name="Land", slug="land", group_slug=None, group_name=None)
    apartments = SimpleNamespace(id=11, category_id=1, name="Apartments", slug="apartments")
    offices = SimpleNamespace(id=21, category_id=2, name="Offices", slug="offices")
    residential_lands = SimpleNamespace(id=31, category_id=3, name="Residential Lands", slug="residential-lands")

    db = MagicMock()
    category_result = MagicMock()
    category_result.scalars.return_value.all.return_value = [residential, commercial, land]
    type_result = MagicMock()
    type_result.scalars.return_value.all.return_value = [apartments, offices, residential_lands]
    db.execute.side_effect = [category_result, type_result]

    response = public_catalog.get_property_taxonomy(db)
    data = response["data"]["data"]
    groups = response["data"]["groups"]

    assert [item["slug"] for item in data] == ["residential", "commercial", "land"]
    assert {item["slug"]: item["group_slug"] for item in data} == {
        "residential": "properties",
        "commercial": "properties",
        "land": "land",
    }
    assert [group["slug"] for group in groups] == ["properties", "land"]
    assert [item["slug"] for item in groups[0]["categories"]] == ["residential", "commercial"]
    assert [item["slug"] for item in groups[1]["categories"]] == ["land"]
    by_slug = {item["slug"]: item for item in data}
    assert [field["key"] for field in by_slug["residential"]["identification_fields"]] == [
        "land_type",
        "floor_number",
        "apartment_number",
        "plot_number",
        "parcel_number",
        "building_number",
    ]
    assert [field["key"] for field in by_slug["land"]["identification_fields"]] == ["plot_number"]


def test_sort_categories_keeps_existing_dco_order() -> None:
    land = SimpleNamespace(slug="land", name="Land")
    commercial = SimpleNamespace(slug="commercial", name="Commercial")
    residential = SimpleNamespace(slug="residential", name="Residential")
    ordered = sort_categories([land, commercial, residential])
    assert [item.slug for item in ordered] == ["residential", "commercial", "land"]
