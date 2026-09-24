from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.live_schema import DlsLocation
from app.utils.api_response import raise_api_error
from app.utils.status_codes import STATUS_BAD_REQUEST


# Canonical API levels match the MLS Location step contract.
DLS_LEVELS = ("gov", "dept", "vill", "hod", "sect")
DLS_PARENTS = {
    "gov": (),
    "dept": ("gov_code",),
    "vill": ("gov_code", "dept_code"),
    "hod": ("gov_code", "dept_code", "vill_code"),
    "sect": ("gov_code", "dept_code", "vill_code", "hod_code"),
}
DLS_CODE_COLUMNS = {
    "gov": DlsLocation.gov_code,
    "dept": DlsLocation.dept_code,
    "vill": DlsLocation.vill_code,
    "hod": DlsLocation.hod_code,
    "sect": DlsLocation.sect_code,
}
DLS_NAME_COLUMNS = {
    "gov": DlsLocation.gov_name,
    "dept": DlsLocation.dept_name,
    "vill": DlsLocation.vill_name,
    "hod": DlsLocation.hod_name,
    "sect": DlsLocation.sect_name,
}
DLS_FILTER_COLUMNS = {
    "gov_code": DlsLocation.gov_code,
    "dept_code": DlsLocation.dept_code,
    "vill_code": DlsLocation.vill_code,
    "hod_code": DlsLocation.hod_code,
    "sect_code": DlsLocation.sect_code,
}


def normalize_dls_level(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    token = str(value).strip().casefold().replace("-", "_")
    aliases = {
        "government": "gov",
        "governorate": "gov",
        "governate": "gov",
        "department": "dept",
        "directorate": "dept",
        "village": "vill",
        "hods": "hod",
        "parcel_name": "hod",
        "section": "sect",
        "sector": "sect",
    }
    token = aliases.get(token, token)
    return token if token in DLS_LEVELS else None


def serialize_dls_item(level: str, row: Any, *, parents: dict[str, str]) -> dict[str, Any]:
    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        code = mapping.get("code")
        name = mapping.get("name")
    elif isinstance(row, (tuple, list)) and len(row) >= 2:
        code, name = row[0], row[1]
    else:
        code, name = getattr(row, "code", None), getattr(row, "name", None)
    item = {"code": code, "name": name, "level": level}
    item.update(parents)
    return item


def list_dls_locations(
    db: Session,
    *,
    level: str,
    gov_code: str | None = None,
    dept_code: str | None = None,
    vill_code: str | None = None,
    hod_code: str | None = None,
    # Backward-compatible aliases for callers still sending government_*.
    government_code: str | None = None,
) -> dict[str, Any]:
    normalized_level = normalize_dls_level(level)
    if not normalized_level:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="INVALID_VALUE",
            message="Unknown DLS level",
            details=[
                {
                    "field": "level",
                    "code": "invalid_value",
                    "message": "level must be one of: gov, dept, vill, hod, sect",
                }
            ],
        )

    filters = {
        "gov_code": (gov_code or government_code or "").strip(),
        "dept_code": (dept_code or "").strip(),
        "vill_code": (vill_code or "").strip(),
        "hod_code": (hod_code or "").strip(),
    }
    parents: dict[str, str] = {}
    for parent in DLS_PARENTS[normalized_level]:
        value = filters[parent]
        if not value:
            raise_api_error(
                status_code=STATUS_BAD_REQUEST,
                code="VALIDATION_ERROR",
                message=f"{parent} is required for DLS {normalized_level} lookup",
                details=[
                    {
                        "field": parent,
                        "code": "missing_required_field",
                        "message": f"{parent} is required when level={normalized_level}",
                    }
                ],
            )
        parents[parent] = value

    code_column = DLS_CODE_COLUMNS[normalized_level]
    name_column = DLS_NAME_COLUMNS[normalized_level]
    stmt = select(code_column.label("code"), name_column.label("name")).distinct()
    for parent, value in parents.items():
        stmt = stmt.where(DLS_FILTER_COLUMNS[parent] == value)
    stmt = stmt.order_by(name_column.asc(), code_column.asc())
    rows = db.execute(stmt).all()
    items = [serialize_dls_item(normalized_level, row, parents=parents) for row in rows]
    return {"level": normalized_level, "items": items, "total": len(items)}


def dls_official_name(
    db: Session,
    *,
    level: str,
    code: str,
    parents: dict[str, str],
) -> str | None:
    normalized_level = normalize_dls_level(level) or level
    code_column = DLS_CODE_COLUMNS[normalized_level]
    name_column = DLS_NAME_COLUMNS[normalized_level]
    stmt = select(name_column).where(code_column == code).distinct()
    for parent, value in parents.items():
        if value:
            # Accept legacy government_code parent keys from older callers.
            filter_key = "gov_code" if parent in {"gov_code", "government_code"} else parent
            stmt = stmt.where(DLS_FILTER_COLUMNS[filter_key] == value)
    value = db.execute(stmt.limit(1)).scalar()
    if isinstance(value, str) and value.strip():
        return value
    if value is None:
        return None
    return None
