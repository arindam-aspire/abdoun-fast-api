from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.live_schema import PropertyOptionValue
from app.utils.api_response import raise_api_error
from app.utils.status_codes import STATUS_BAD_REQUEST


OPTION_GROUPS = frozenset(
    {
        "furnishing_status",
        "floor",
        "listing_purpose",
        "completion_status",
        "direction",
        "land_type",
    }
)

VALUE_ALIASES = {
    "furnishing_status": {
        "semi_furnished": "semi-furnished",
        "semifurnished": "semi-furnished",
    },
    "listing_purpose": {
        "sale+rent": "sale-or-rent",
        "sale_and_rent": "sale-or-rent",
        "sale_or_rent": "sale-or-rent",
    },
    "completion_status": {
        "offplan": "off-plan",
        "off_plan": "off-plan",
        "off plan": "off-plan",
    },
    "direction": {
        "ne": "northeast",
        "nw": "northwest",
        "se": "southeast",
        "sw": "southwest",
        "north-east": "northeast",
        "north-west": "northwest",
        "south-east": "southeast",
        "south-west": "southwest",
    },
}

REJECTED_COMPLETION_STATUS_TOKENS = frozenset(
    {"under-construction", "underconstruction", "under_construction"}
)

_ID_FIELD_NAMES = frozenset(
    {
        "floor",
        "floor_id",
        "furnishing_status_id",
        "furnishing_status",
        "furniture_status",
        "furnishing",
        "land_type",
        "land_type_id",
    }
)
_NUMERIC_FIELD_NAMES = frozenset({"floor_number"})


def normalized_option_token(value: Any) -> str:
    token = re.sub(r"[\s_]+", "-", str(value or "").strip().casefold())
    return re.sub(r"-+", "-", token).strip("-")


def normalize_group_key(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    split_camel = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(value).strip())
    return normalized_option_token(split_camel).replace("-", "_")


def serialize_option(option: PropertyOptionValue) -> dict[str, Any]:
    return {
        "id": option.id,
        "group": option.group_key,
        "name": option.name,
        "slug": option.slug,
        "numeric_value": option.numeric_value,
        "display_order": option.display_order,
        "is_active": bool(option.is_active),
    }


def list_property_options(
    db: Session,
    *,
    group: str | None = None,
    is_active: bool | None = True,
) -> list[PropertyOptionValue]:
    stmt = select(PropertyOptionValue)
    normalized_group = normalize_group_key(group)
    if normalized_group:
        stmt = stmt.where(PropertyOptionValue.group_key == normalized_group)
    if is_active is not None:
        stmt = stmt.where(PropertyOptionValue.is_active.is_(is_active))
    return list(
        db.execute(
            stmt.order_by(
                PropertyOptionValue.group_key.asc(),
                PropertyOptionValue.display_order.asc(),
                PropertyOptionValue.id.asc(),
            )
        ).scalars().all()
    )


def _field_name(field: str) -> str:
    token = field.rsplit(".", 1)[-1]
    return normalize_group_key(token) or token.casefold()


def coerce_option_input(value: Any) -> Any:
    if isinstance(value, dict):
        for key in ("id", "numeric_value", "numericValue", "slug", "name", "value"):
            if value.get(key) not in (None, ""):
                return value[key]
    return value


def _numeric_option_value(value: Any) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def resolve_property_option(
    db: Session,
    *,
    group: str,
    value: Any,
    field: str,
) -> PropertyOptionValue:
    group_key = normalize_group_key(group) or group
    value = coerce_option_input(value)
    token = VALUE_ALIASES.get(group_key, {}).get(normalized_option_token(value), normalized_option_token(value))
    if group_key == "completion_status" and (
        token in REJECTED_COMPLETION_STATUS_TOKENS
        or normalized_option_token(value) in REJECTED_COMPLETION_STATUS_TOKENS
    ):
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="INVALID_VALUE",
            message="Under Construction is not a valid completion status",
            details=[
                {
                    "field": field,
                    "code": "invalid_value",
                    "message": "Under Construction is not accepted. Use Off Plan or another active completion status",
                }
            ],
        )
    numeric = _numeric_option_value(value)
    field_token = _field_name(field)
    prefer_id = field_token in _ID_FIELD_NAMES
    prefer_numeric = field_token in _NUMERIC_FIELD_NAMES

    stmt_base = select(PropertyOptionValue).where(
        PropertyOptionValue.group_key == group_key,
        PropertyOptionValue.is_active.is_(True),
    )

    def _first(condition) -> PropertyOptionValue | None:
        return db.execute(stmt_base.where(condition)).scalars().first()

    option = None
    if numeric is not None and prefer_id:
        option = _first(PropertyOptionValue.id == numeric)
    if option is None and numeric is not None and prefer_numeric:
        option = _first(PropertyOptionValue.numeric_value == numeric)
        if option is None:
            option = _first(PropertyOptionValue.slug == str(numeric))
    if option is None and token:
        option = _first(PropertyOptionValue.slug == token)
    if option is None and str(value or "").strip():
        option = _first(PropertyOptionValue.name.ilike(str(value).strip()))
    if option is None and numeric is not None:
        option = _first(PropertyOptionValue.id == numeric)
    if option is None and numeric is not None:
        option = _first(PropertyOptionValue.numeric_value == numeric)
    if option is None:
        raise_api_error(
            status_code=STATUS_BAD_REQUEST,
            code="INVALID_VALUE",
            message=f"Invalid value for {field}",
            details=[{"field": field, "code": "invalid_value", "message": "Select an active master-data value"}],
        )
    return option
