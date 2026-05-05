from dataclasses import dataclass

from app.api.v1.deps.locations import get_location_service
from app.api.v1.deps.property_taxonomy import get_property_taxonomy_service
from app.api.v1.routes import locations as legacy_locations
from app.api.v1.routes import property_taxonomy as legacy_property_taxonomy
from app.domains.taxonomy.deps import get_taxonomy_service
from app.domains.taxonomy.router import router as refactored_router
from tests.refactor_parity.assertions import assert_json_shape_parity, assert_status_parity
from tests.refactor_parity.parity_client import build_refactored_client


@dataclass(slots=True)
class _LegacyLocationService:
    def get_location_taxonomy(self) -> dict:
        return {"data": [{"id": 1, "name": "City", "areas": [{"id": 10, "name": "Area"}]}], "total": 1}


@dataclass(slots=True)
class _LegacyPropertyTaxonomyService:
    def get_property_taxonomy(self) -> dict:
        return {
            "data": [{"id": 5, "name": "Residential", "slug": "res", "property_types": []}],
            "total": 1,
        }


@dataclass(slots=True)
class _RefactoredTaxonomyService:
    def get_location_taxonomy(self) -> dict:
        return {"data": [{"id": 1, "name": "City", "areas": [{"id": 10, "name": "Area"}]}], "total": 1}

    def get_property_taxonomy(self) -> dict:
        return {
            "data": [{"id": 5, "name": "Residential", "slug": "res", "property_types": []}],
            "total": 1,
        }


def test_taxonomy_parity_for_location_and_property_taxonomy_endpoints() -> None:
    legacy_app = build_refactored_client(legacy_locations.router)
    legacy_property_app = build_refactored_client(legacy_property_taxonomy.router)
    refactored_app = build_refactored_client(refactored_router)

    legacy_app.app.dependency_overrides[get_location_service] = lambda: _LegacyLocationService()
    legacy_property_app.app.dependency_overrides[get_property_taxonomy_service] = (
        lambda: _LegacyPropertyTaxonomyService()
    )
    refactored_app.app.dependency_overrides[get_taxonomy_service] = lambda: _RefactoredTaxonomyService()

    location_legacy = legacy_app.get("/location-taxonomy")
    location_refactored = refactored_app.get("/location-taxonomy")
    assert_status_parity(location_legacy.status_code, location_refactored.status_code)
    assert_json_shape_parity(location_legacy.json(), location_refactored.json())

    property_legacy = legacy_property_app.get("/property-taxonomy")
    property_refactored = refactored_app.get("/property-taxonomy")
    assert_status_parity(property_legacy.status_code, property_refactored.status_code)
    assert_json_shape_parity(property_legacy.json(), property_refactored.json())

