from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.catalog_features import (
    feature_applies_to_property_type,
    filter_features,
    is_shared_feature,
    resolve_feature_scope,
)


def _feature(**kwargs):
    defaults = {
        "id": 1,
        "name": "Feature",
        "slug": "feature",
        "category_id": 1,
        "property_type_id": None,
        "feature_group": "FEATURE",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_apartment_filter_includes_type_features_and_shared_amenities() -> None:
    apartments = SimpleNamespace(id=11, category_id=1, slug="apartments", name="Apartments")
    features = [
        _feature(id=1, name="Duplex", slug="duplex-residential-apartments-feature", feature_group="FEATURE"),
        _feature(id=2, name="Independent Villa", slug="independent-villa-residential-villas-feature"),
        _feature(
            id=3,
            name="Parking",
            slug="parking-residential-common-amenity",
            feature_group="AMENITY",
        ),
        _feature(
            id=4,
            name="Elevator",
            slug="elevator-commercial-common-amenity",
            category_id=2,
            feature_group="AMENITY",
        ),
    ]

    selected = filter_features(features, property_type=apartments)
    assert [feature.name for feature in selected] == ["Duplex", "Parking"]
    assert is_shared_feature(selected[1]) is True
    assert feature_applies_to_property_type(features[1], apartments) is False


def test_type_id_mapping_is_used_when_present() -> None:
    apartments = SimpleNamespace(id=11, category_id=1, slug="apartments", name="Apartments")
    linked = _feature(id=9, name="Flat", slug="custom-slug", property_type_id=11, feature_group="FEATURE")
    assert feature_applies_to_property_type(linked, apartments) is True


def test_ambiguous_property_type_slug_requires_category() -> None:
    from unittest.mock import MagicMock

    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = [
        SimpleNamespace(id=1, category_id=1, slug="villas"),
        SimpleNamespace(id=2, category_id=2, slug="villas"),
    ]
    with pytest.raises(HTTPException) as exc_info:
        resolve_feature_scope(db, property_type="villas")
    assert exc_info.value.detail["details"][0]["field"] == "property_type"
