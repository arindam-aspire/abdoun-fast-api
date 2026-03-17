"""Unit tests for app.services.geo_search_service."""
from unittest.mock import MagicMock

from app.schemas.property import BoundsFilter, PolygonFilter, PropertySearchRequest
from app.services.geo_search_service import GeoSearchService


def test_geo_search_bounds():
    repo = MagicMock()
    repo.geo_search.return_value = []
    svc = GeoSearchService(repo)
    req = PropertySearchRequest(
        mode="bounds",
        bounds=BoundsFilter(min_lng=0, min_lat=0, max_lng=1, max_lat=1),
        limit=10,
    )
    out = svc.search(req)
    assert out.total == 0
    assert out.items == []
    repo.geo_search.assert_called_once_with(bounds=(0, 0, 1, 1), polygon_geojson=None, limit=10)


def test_geo_search_polygon():
    repo = MagicMock()
    repo.geo_search.return_value = []
    svc = GeoSearchService(repo)
    geojson = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    req = PropertySearchRequest(
        mode="polygon",
        polygon=PolygonFilter(geojson=geojson),
        limit=5,
    )
    out = svc.search(req)
    assert out.total == 0
    repo.geo_search.assert_called_once()
    call_kw = repo.geo_search.call_args[1]
    assert call_kw["bounds"] is None
    assert "polygon_geojson" in call_kw
    assert call_kw["limit"] == 5
