"""Unit tests for app.domains.shared.pagination.

Coverage:
- calculate_pagination: page / offset / totalPages computation
- calculate_pagination: edge cases (zero total, last page, over-page)
- build_paginated_response: dict shape and field aliasing
- SortParams: order normalisation
- resolve_sort_column: allow-list enforcement
- PaginatedResponse: Pydantic schema round-trip
- PageParams: alias parsing
"""

import pytest

from app.domains.shared.pagination import (
    PageParams,
    PaginatedResponse,
    PaginationMeta,
    SortParams,
    build_paginated_response,
    calculate_pagination,
    resolve_sort_column,
)


# ---------------------------------------------------------------------------
# calculate_pagination
# ---------------------------------------------------------------------------


class TestCalculatePagination:
    def test_first_page_standard(self):
        meta = calculate_pagination(page=1, page_size=20, total=100)
        assert meta.page == 1
        assert meta.page_size == 20
        assert meta.total == 100
        assert meta.offset == 0
        assert meta.total_pages == 5
        assert meta.has_next is True
        assert meta.has_previous is False

    def test_middle_page(self):
        meta = calculate_pagination(page=3, page_size=20, total=100)
        assert meta.offset == 40
        assert meta.total_pages == 5
        assert meta.has_next is True
        assert meta.has_previous is True

    def test_last_page(self):
        meta = calculate_pagination(page=5, page_size=20, total=100)
        assert meta.offset == 80
        assert meta.has_next is False
        assert meta.has_previous is True

    def test_partial_last_page(self):
        meta = calculate_pagination(page=3, page_size=20, total=45)
        assert meta.total_pages == 3
        assert meta.has_next is False

    def test_single_page(self):
        meta = calculate_pagination(page=1, page_size=50, total=10)
        assert meta.total_pages == 1
        assert meta.has_next is False
        assert meta.has_previous is False

    def test_zero_total(self):
        meta = calculate_pagination(page=1, page_size=20, total=0)
        assert meta.total == 0
        assert meta.total_pages == 0
        assert meta.has_next is False
        assert meta.has_previous is False

    def test_page_beyond_total_pages(self):
        """Requesting page 99 with only 2 pages: has_next stays False."""
        meta = calculate_pagination(page=99, page_size=20, total=40)
        assert meta.total_pages == 2
        assert meta.has_next is False
        assert meta.has_previous is True

    def test_page_one_with_exact_total(self):
        """Exactly page_size items → 1 page, no next."""
        meta = calculate_pagination(page=1, page_size=20, total=20)
        assert meta.total_pages == 1
        assert meta.has_next is False

    def test_page_clamped_to_one_on_zero(self):
        """Defensive: page=0 should be treated as page=1."""
        meta = calculate_pagination(page=0, page_size=20, total=100)
        assert meta.page == 1
        assert meta.offset == 0

    def test_page_size_clamped_to_one_on_zero(self):
        meta = calculate_pagination(page=1, page_size=0, total=100)
        assert meta.page_size == 1
        assert meta.total_pages == 100

    def test_large_dataset(self):
        meta = calculate_pagination(page=100, page_size=50, total=10_000)
        assert meta.offset == 4950
        assert meta.total_pages == 200
        assert meta.has_next is True
        assert meta.has_previous is True

    def test_single_item(self):
        meta = calculate_pagination(page=1, page_size=20, total=1)
        assert meta.total_pages == 1
        assert meta.has_next is False

    def test_offset_formula(self):
        for page in range(1, 6):
            meta = calculate_pagination(page=page, page_size=10, total=50)
            assert meta.offset == (page - 1) * 10


# ---------------------------------------------------------------------------
# build_paginated_response
# ---------------------------------------------------------------------------


class TestBuildPaginatedResponse:
    def _meta(self, page=1, page_size=20, total=100) -> PaginationMeta:
        return calculate_pagination(page=page, page_size=page_size, total=total)

    def test_basic_shape(self):
        items = [{"id": 1}, {"id": 2}]
        meta = self._meta(page=1, page_size=2, total=10)
        result = build_paginated_response(items=items, meta=meta)

        assert result["items"] == items
        assert result["total"] == 10
        assert result["page"] == 1
        assert result["pageSize"] == 2
        assert result["totalPages"] == 5
        assert result["hasNext"] is True
        assert result["hasPrevious"] is False

    def test_pageSize_alias_present(self):
        """Response must use camelCase `pageSize`, not snake_case `page_size`."""
        meta = self._meta()
        result = build_paginated_response(items=[], meta=meta)
        assert "pageSize" in result
        assert "page_size" not in result

    def test_extra_fields_merged(self):
        meta = self._meta()
        result = build_paginated_response(items=[], meta=meta, extra={"custom": "value"})
        assert result["custom"] == "value"

    def test_empty_items(self):
        meta = self._meta(total=0)
        result = build_paginated_response(items=[], meta=meta)
        assert result["items"] == []
        assert result["total"] == 0
        assert result["totalPages"] == 0
        assert result["hasNext"] is False
        assert result["hasPrevious"] is False

    def test_last_page_flags(self):
        meta = self._meta(page=5, total=100)
        result = build_paginated_response(items=[], meta=meta)
        assert result["hasNext"] is False
        assert result["hasPrevious"] is True


# ---------------------------------------------------------------------------
# SortParams
# ---------------------------------------------------------------------------


class TestSortParams:
    def test_defaults(self):
        p = SortParams()
        assert p.sort_by == "createdAt"
        assert p.sort_order == "desc"

    def test_valid_asc(self):
        p = SortParams(sortOrder="asc")
        assert p.sort_order == "asc"

    def test_valid_desc(self):
        p = SortParams(sortOrder="desc")
        assert p.sort_order == "desc"

    def test_upper_case_coerced(self):
        p = SortParams(sortOrder="DESC")
        assert p.sort_order == "desc"

    def test_invalid_value_coerced_to_desc(self):
        p = SortParams(sortOrder="random")
        assert p.sort_order == "desc"

    def test_alias_accepted(self):
        """sortBy alias maps to sort_by field."""
        p = SortParams(sortBy="fullName")
        assert p.sort_by == "fullName"

    def test_snake_case_also_accepted(self):
        p = SortParams(sort_by="fullName", sort_order="asc")
        assert p.sort_by == "fullName"
        assert p.sort_order == "asc"


# ---------------------------------------------------------------------------
# resolve_sort_column
# ---------------------------------------------------------------------------


class TestResolveSortColumn:
    def test_known_key_returns_mapped_value(self):
        allow = {"createdAt": "col_created_at", "name": "col_name"}
        assert resolve_sort_column("createdAt", allow, "col_default") == "col_created_at"

    def test_unknown_key_returns_default(self):
        allow = {"createdAt": "col_created_at"}
        assert resolve_sort_column("unknownField", allow, "col_default") == "col_default"

    def test_empty_allow_list_returns_default(self):
        assert resolve_sort_column("anything", {}, "col_default") == "col_default"

    def test_sql_injection_style_key_falls_back(self):
        """Ensure unsafe strings fall back to default without hitting SQL."""
        allow = {"createdAt": "col_created_at"}
        result = resolve_sort_column("1; DROP TABLE users;--", allow, "col_default")
        assert result == "col_default"


# ---------------------------------------------------------------------------
# PageParams
# ---------------------------------------------------------------------------


class TestPageParams:
    def test_defaults(self):
        p = PageParams()
        assert p.page == 1
        assert p.page_size == 20

    def test_alias_pageSize(self):
        p = PageParams.model_validate({"pageSize": 50, "page": 2})
        assert p.page_size == 50
        assert p.page == 2

    def test_snake_case_also_valid(self):
        p = PageParams(page_size=30)
        assert p.page_size == 30

    def test_page_must_be_ge_1(self):
        with pytest.raises(Exception):
            PageParams(page=0)

    def test_page_size_must_be_ge_1(self):
        with pytest.raises(Exception):
            PageParams(page_size=0)

    def test_page_size_max_200(self):
        with pytest.raises(Exception):
            PageParams(page_size=201)


# ---------------------------------------------------------------------------
# PaginatedResponse (Pydantic schema)
# ---------------------------------------------------------------------------


class TestPaginatedResponse:
    def test_round_trip(self):
        data = {
            "items": [1, 2, 3],
            "total": 30,
            "page": 1,
            "pageSize": 3,
            "totalPages": 10,
            "hasNext": True,
            "hasPrevious": False,
        }
        r = PaginatedResponse[int].model_validate(data)
        assert r.total == 30
        assert r.pageSize == 3
        assert r.hasNext is True

    def test_serialisation_uses_camel_keys(self):
        meta = calculate_pagination(page=2, page_size=10, total=100)
        payload = build_paginated_response(items=["a", "b"], meta=meta)
        r = PaginatedResponse[str].model_validate(payload)
        dumped = r.model_dump()
        assert "pageSize" in dumped
        assert "totalPages" in dumped
        assert "hasNext" in dumped
        assert "hasPrevious" in dumped
