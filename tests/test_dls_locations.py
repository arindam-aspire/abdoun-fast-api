from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.dls_locations import list_dls_locations, normalize_dls_level, serialize_dls_item
from app.services.property_submissions import validate_duplicate_property


def test_normalize_dls_level_aliases() -> None:
    assert normalize_dls_level("GOV") == "gov"
    assert normalize_dls_level("directorate") == "dept"
    assert normalize_dls_level("village") == "vill"
    assert normalize_dls_level("section") == "sect"
    assert normalize_dls_level("unknown") is None


def test_gov_level_does_not_require_parent_codes() -> None:
    db = MagicMock()
    db.execute.return_value.all.return_value = [("1", "Capital Governorate"), ("2", "Irbid")]
    result = list_dls_locations(db, level="gov")
    assert result["level"] == "gov"
    assert result["total"] == 2
    assert result["items"][0]["code"] == "1"
    assert result["items"][0]["name"] == "Capital Governorate"


def test_dept_level_requires_gov_code() -> None:
    with pytest.raises(HTTPException) as exc_info:
        list_dls_locations(MagicMock(), level="dept")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["details"][0]["field"] == "gov_code"


def test_sect_level_requires_full_parent_path() -> None:
    with pytest.raises(HTTPException) as exc_info:
        list_dls_locations(MagicMock(), level="sect", gov_code="1", dept_code="1", vill_code="1")
    assert exc_info.value.detail["details"][0]["field"] == "hod_code"


def test_serialize_dls_item_includes_parent_codes() -> None:
    item = serialize_dls_item("dept", ("11", "Amman Lands"), parents={"gov_code": "1"})
    assert item == {"code": "11", "name": "Amman Lands", "level": "dept", "gov_code": "1"}


def test_duplicate_validation_uses_dls_codes_with_parcel() -> None:
    from uuid import uuid4

    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = uuid4()
    with pytest.raises(HTTPException) as exc_info:
        validate_duplicate_property(
            db,
            {
                "location": {
                    "gov_code": "1",
                    "dept_code": "1",
                    "vill_code": "1",
                    "hod_code": "2",
                    "sect_code": "0",
                    "parcel_number": "44",
                }
            },
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "DUPLICATE_PROPERTY"
