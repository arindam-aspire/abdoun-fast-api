from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.app_defaults import get_currency_symbols
from app.core.config import get_settings
from app.models.deal_closure import PropertyDealClosure
from app.models.live_schema import (
    AgencyMaster,
    Area,
    City,
    Feature,
    PropertyCategory,
    PropertyListingSubmission,
    PropertyMedia,
    PropertyType,
    User,
    UserPropertyFavorite,
)
from app.services.media_urls import resolve_readable_media_url
from app.services.property_submissions import (
    _assigned_agent_id,
    can_view_submission,
    displayed_reference_number,
    serialize_agent_contact_by_id,
    serialize_property_detail_workflow,
    show_location_for_submission,
    stable_property_hash,
)
from app.utils.status_codes import STATUS_NOT_FOUND


PUBLIC_STATUSES = {"active"}
DEAL_CLOSED_STATUS = "APPROVED"
AGENT_CONTACT_VISIBLE_ROLES = frozenset(
    {"owner", "registered_user", "agent", "admin", "super_admin"}
)


def can_view_property_agent_contact(roles: tuple[str, ...]) -> bool:
    normalized = {role.casefold() for role in roles}
    if normalized.intersection({"agency_admin", "agency"}):
        normalized.add("admin")
    if "user" in normalized:
        normalized.add("registered_user")
    return not normalized.isdisjoint(AGENT_CONTACT_VISIBLE_ROLES)


ANONYMOUS_HIDDEN_DETAIL_KEYS = frozenset(
    {"agency", "assigned_agent_id", "owners", "owner"}
)


def _strip_anonymous_property_detail_fields(detail: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in detail.items()
        if key not in ANONYMOUS_HIDDEN_DETAIL_KEYS
    }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def pagination_meta(total: int, page: int, page_size: int) -> dict[str, Any]:
    total_pages = math.ceil(total / page_size) if total else 1
    return {
        "total": total,
        "page": page,
        "pageSize": page_size,
        "totalPages": total_pages,
        "hasNext": page < total_pages,
        "hasPrevious": page > 1,
    }


def localized_text(value: str | None) -> dict[str, str]:
    text = value or ""
    return {"en": text, "ar": text, "fr": text, "esp": text}


def localized_nullable_text(value: str | None) -> dict[str, str | None]:
    return {"en": value, "ar": value, "fr": value, "esp": value}


def _int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _slug(value: Any) -> str:
    return str(value or "").strip().casefold()


def _token(value: Any) -> str:
    return _slug(value).replace("_", "-").replace(" ", "-")


def _text_match(value: Any, query: str | None) -> bool:
    if not query:
        return True
    return _slug(query) in _slug(value)


def _empty_media_for_listing() -> dict[str, Any]:
    return {
        "thumbnail": None,
        "images": [],
        "videos": [],
        "virtual_tour_url": None,
        "floor_plan_images": [],
        "documents": [],
    }


def _media_from_property_media_rows(rows: list[PropertyMedia]) -> dict[str, Any] | None:
    if not rows:
        return None
    media = dict(_empty_media_for_listing())
    images: list[dict[str, Any]] = []
    videos: list[dict[str, Any]] = []
    floor_plans: list[dict[str, Any]] = []
    documents: list[dict[str, Any]] = []

    for row in rows:
        url = resolve_readable_media_url(row.url)
        if not url:
            continue
        item = {
            "id": row.id,
            "url": url,
            "thumb_url": resolve_readable_media_url(row.thumb_url) or url,
            "is_primary": bool(row.is_primary),
            "order": int(row.display_order or 0),
            "caption": row.caption,
        }
        if row.media_type == "image":
            images.append(item)
        elif row.media_type == "video":
            videos.append(item)
        elif row.media_type == "floor_plan":
            floor_plans.append(item)
        elif row.media_type == "document":
            documents.append(item)

    images.sort(key=lambda item: (not item["is_primary"], item["order"], item["id"]))
    videos.sort(key=lambda item: (item["order"], item["id"]))
    floor_plans.sort(key=lambda item: (item["order"], item["id"]))
    documents.sort(key=lambda item: (item["order"], item["id"]))

    media.update(
        {
            "thumbnail": images[0]["url"] if images else None,
            "images": images,
            "videos": videos,
            "floor_plan_images": floor_plans,
            "documents": documents,
        }
    )
    return media


def _media_for_listing(payload: dict[str, Any], *, property_media_rows: list[PropertyMedia] | None = None) -> dict[str, Any]:
    from_table = _media_from_property_media_rows(property_media_rows or [])
    if from_table and (from_table["images"] or from_table["videos"] or from_table["documents"] or from_table["floor_plan_images"]):
        source = payload.get("media_documents") or {}
        if isinstance(source, dict):
            from_table["virtual_tour_url"] = source.get("virtual_tour_url")
        return from_table

    media = dict(_empty_media_for_listing())
    source = payload.get("media_documents") or {}
    images = []
    for index, image in enumerate(source.get("images") or []):
        url = resolve_readable_media_url(image.get("url") if isinstance(image, dict) else None)
        if not url:
            continue
        images.append(
            {
                "id": index + 1,
                "url": url,
                "thumb_url": url,
                "is_primary": bool(image.get("is_primary")) or index == 0,
                "order": _int(image.get("display_order"), index),
                "caption": image.get("file_name"),
            }
        )
    videos = []
    if source.get("youtube_url"):
        videos.append(
            {
                "id": 1,
                "url": source.get("youtube_url"),
                "thumb_url": source.get("youtube_url"),
                "is_primary": True,
                "order": 0,
                "caption": None,
            }
        )
    documents = []
    for index, document in enumerate(source.get("documents") or []):
        url = resolve_readable_media_url(document.get("url") if isinstance(document, dict) else None)
        if not url:
            continue
        documents.append(
            {
                "id": index + 1,
                "url": url,
                "thumb_url": url,
                "is_primary": index == 0,
                "order": _int(document.get("display_order"), index),
                "caption": document.get("file_name"),
            }
        )
    media.update(
        {
            "thumbnail": images[0]["url"] if images else None,
            "images": images,
            "videos": videos,
            "documents": documents,
            "virtual_tour_url": source.get("virtual_tour_url"),
        }
    )
    return media


def _media_for_details(
    payload: dict[str, Any],
    *,
    property_media_rows: list[PropertyMedia] | None = None,
) -> dict[str, Any]:
    media = _media_for_listing(payload, property_media_rows=property_media_rows)
    media["videos"] = [video.get("url") for video in media["videos"] if video.get("url")]
    return media


def _taxonomy_maps(db: Session) -> tuple[dict[int, PropertyCategory], dict[int, PropertyType], dict[int, City], dict[int, Area]]:
    categories = {item.id: item for item in db.execute(select(PropertyCategory)).scalars().all()}
    types = {item.id: item for item in db.execute(select(PropertyType)).scalars().all()}
    cities = {item.id: item for item in db.execute(select(City)).scalars().all()}
    areas = {item.id: item for item in db.execute(select(Area)).scalars().all()}
    return categories, types, cities, areas


def _agency_for_submission(db: Session, submission: PropertyListingSubmission, user: User | None = None) -> AgencyMaster | None:
    if not bool(getattr(submission, "route_through_agency", False)):
        return None
    agency_id = submission.agency_id or (user.agency_id if user else None)
    if not agency_id:
        return None
    return db.get(AgencyMaster, agency_id)


def _agency_payload(agency: AgencyMaster | None) -> dict[str, Any] | None:
    if not agency:
        return None
    return {
        "agency_id": str(agency.id),
        "agency_name": agency.agency_name,
        "agency_trade_name": agency.agency_trade_name,
        "email": agency.email,
        "phone": agency.phone,
        "website": agency.website,
    }


def _owners(payload: dict[str, Any]) -> list[dict[str, Any]]:
    owners = ((payload.get("owner_information") or {}).get("owners") or [])
    serialized = []
    for index, owner in enumerate(owners):
        serialized.append(
            {
                "owner_id": owner.get("id") or str(index + 1),
                "full_name": owner.get("full_name") or "",
                "email": owner.get("email"),
                "phone": owner.get("phone"),
                "nationality": owner.get("nationality"),
                "ssi": owner.get("ssi") or owner.get("social_security_id"),
                "address": owner.get("address"),
                "documents": owner.get("documents") or [],
                "is_active": True,
            }
        )
    return serialized


def _currency_payload(code: str | None) -> dict[str, str]:
    settings = get_settings()
    default_currency = settings.default_currency
    normalized = (code or default_currency).strip().upper() or default_currency
    symbols = get_currency_symbols()
    return {
        "code": normalized,
        "symbol": symbols.get(normalized, normalized),
    }


def _feature_ids(payload: dict[str, Any]) -> list[int]:
    return [_int(value) for value in ((payload.get("amenities") or {}).get("feature_ids") or []) if _int(value)]


def _feature_list(db: Session, payload: dict[str, Any]) -> list[dict[str, Any]]:
    feature_ids = _feature_ids(payload)
    if not feature_ids:
        return []

    features = {
        feature.id: feature
        for feature in db.execute(select(Feature).where(Feature.id.in_(feature_ids))).scalars().all()
    }
    items: list[dict[str, Any]] = []
    for feature_id in feature_ids:
        feature = features.get(feature_id)
        feature_group = str(feature.feature_group if feature else "FEATURE").upper()
        items.append(
            {
                "id": feature_id,
                "feature_group": "AMENITIES" if feature_group in {"AMENITY", "AMENITIES"} else "FEATURE",
            }
        )
    return items


def _map_embed_url(*, latitude: float | None, longitude: float | None, query: str) -> str | None:
    settings = get_settings()
    base_url = settings.google_maps_embed_base_url
    zoom = settings.google_maps_embed_zoom
    if latitude is not None and longitude is not None:
        return f"{base_url}?q={latitude},{longitude}&z={zoom}&output=embed"
    if query.strip():
        return f"{base_url}?q={quote(query.strip())}&z={zoom}&output=embed"
    return None


def _load_property_media(db: Session, property_id: UUID) -> list[PropertyMedia]:
    return list(
        db.execute(
            select(PropertyMedia)
            .where(PropertyMedia.property_id == property_id)
            .order_by(PropertyMedia.display_order.asc().nullslast(), PropertyMedia.id.asc())
        ).scalars().all()
    )


def serialize_property_listing(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    submitter: User | None = None,
    favorite_id: UUID | None = None,
    user_id: UUID | None = None,
    include_agent: bool = False,
    include_owners: bool = False,
) -> dict[str, Any]:
    payload = submission.payload or {}
    basic = payload.get("basic_information") or {}
    location = payload.get("location") or {}
    details = payload.get("property_details") or {}
    pricing = payload.get("pricing") or {}
    categories, types, cities, areas = _taxonomy_maps(db)
    category = categories.get(_int(basic.get("category_id")))
    property_type = types.get(_int(basic.get("type_id")))
    city = cities.get(_int(location.get("city_id")))
    area = areas.get(_int(location.get("area_id")))
    agency = _agency_for_submission(db, submission, submitter)
    property_id = submission.property_id or submission.id
    property_hash = stable_property_hash(property_id)
    listing_type = "rent" if basic.get("listing_purpose") == "rent" else "sale"
    address = localized_text(location.get("address") or (area.name if area else city.name if city else ""))
    media = _media_for_listing(payload, property_media_rows=_load_property_media(db, property_id))
    settings = get_settings()
    latitude = _float(location.get("latitude") or location.get("lat"))
    longitude = _float(location.get("longitude") or location.get("lng"))
    show_location = show_location_for_submission(submission, payload)
    location_query = ", ".join(
        part
        for part in [
            location.get("address"),
            area.name if area else None,
            city.name if city else None,
            settings.default_country,
        ]
        if part
    )
    map_embed_url = location.get("map_embed_url") or _map_embed_url(
        latitude=latitude,
        longitude=longitude,
        query=location_query,
    )
    location_payload = {
        "country_id": settings.default_country_id,
        "country": settings.default_country,
        "city_id": city.id if city else 0,
        "city": city.name if city else "",
        "region_id": area.id if area else 0,
        "region": area.name if area else "",
        "address": address,
        "latitude": latitude,
        "longitude": longitude,
        "map_embed_url": map_embed_url,
        "show_location": show_location,
    }

    item: dict[str, Any] = {
        "id": property_hash,
        "property_id": str(property_id),
        "reference_number": displayed_reference_number(submission, payload=payload, property_id=property_id),
        "route_through_agency": bool(getattr(submission, "route_through_agency", False)),
        "agency_id": str(submission.agency_id) if submission.agency_id else None,
        "title": localized_text(basic.get("title") or settings.untitled_property_title),
        "description": localized_nullable_text(basic.get("description")),
        "price": str(pricing.get("price") or "0"),
        "currency": _currency_payload(pricing.get("currency")),
        "status": submission.status,
        "category": category.slug if category else str(basic.get("category_id") or ""),
        "searchPropertyType": property_type.slug if property_type else str(basic.get("type_id") or ""),
        "city": city.name if city else "",
        "areaName": area.name if area else "",
        "propertyType": property_type.name if property_type else "",
        "media": media,
        "location": location_payload,
        "location_detail": dict(location_payload),
        "show_location": show_location,
        "beds": _int(details.get("bedrooms")),
        "baths": _int(details.get("bathrooms")),
        "area": str(details.get("built_up_area")) if details.get("built_up_area") is not None else None,
        "acres": None,
        "highlights": basic.get("description") or "",
        "badges": [settings.exclusive_badge_label] if bool(basic.get("is_exclusive")) else [],
        "handover": details.get("completion_status"),
        "paymentPlan": pricing.get("payment_method"),
        "validatedDate": iso(submission.reviewed_at) or iso(submission.updated_at) or iso(submission.created_at),
        "brokerName": agency.agency_trade_name if agency else "",
        "brokerLogo": agency.logo_url if agency else None,
        "agency": _agency_payload(agency),
        "is_exclusive": bool(basic.get("is_exclusive")),
        "is_favourite": favorite_id is not None,
        "favourite_id": str(favorite_id) if favorite_id else None,
        "property_hash": str(property_hash),
        "property_hash_id": property_hash,
        "user_id": str(user_id) if user_id else None,
        "listing_type": listing_type,
    }
    if include_owners:
        item["owners"] = _owners(payload)
        item["guard_name"] = details.get("guard_name")
        item["guard_phone_number"] = details.get("guard_phone_number")
    if include_agent:
        assigned_agent_id = _assigned_agent_id(submission)
        agent = (
            serialize_agent_contact_by_id(
                db,
                assigned_agent_id,
                contact_enabled=True,
            )
            if assigned_agent_id
            else None
        )
        if agent is not None:
            item["agent"] = agent
    return item


def serialize_property_detail(
    db: Session,
    submission: PropertyListingSubmission,
    *,
    submitter: User | None = None,
    actor_user_id: UUID | None = None,
    actor_roles: tuple[str, ...] = (),
    actor_agency_id: UUID | None = None,
    include_private_fields: bool = True,
) -> dict[str, Any]:
    listing = serialize_property_listing(
        db,
        submission,
        submitter=submitter,
        include_owners=include_private_fields,
    )
    payload = submission.payload or {}
    basic = payload.get("basic_information") or {}
    details = payload.get("property_details") or {}
    pricing = payload.get("pricing") or {}
    settings = get_settings()
    agency = _agency_for_submission(db, submission, submitter)
    property_hash = listing["id"]
    listing_type = listing["listing_type"]
    property_id = submission.property_id or submission.id
    workflow = serialize_property_detail_workflow(
        db,
        submission,
        actor_user_id=actor_user_id,
        actor_roles=actor_roles,
        actor_agency_id=actor_agency_id,
    )
    is_authenticated = include_private_fields
    workflow_payload = dict(workflow)
    if not is_authenticated:
        workflow_payload.pop("assigned_agent_id", None)

    assigned_agent_id = workflow.get("assigned_agent_id")
    agent = (
        serialize_agent_contact_by_id(
            db,
            assigned_agent_id,
            contact_enabled=is_authenticated,
        )
        if assigned_agent_id
        else None
    )

    detail = {
        **listing,
        **workflow_payload,
        "id": property_hash,
        "url": None,
        "property_type": listing["propertyType"],
        "listing_type": listing_type,
        "selling_price_amount": _float(pricing.get("price")) if listing_type == "sale" else None,
        "selling_price_currency": pricing.get("currency") or settings.default_currency,
        "rent_price_amount": _float(pricing.get("price")) if listing_type == "rent" else None,
        "rent_price_currency": pricing.get("currency") or settings.default_currency,
        "bedrooms": _int(details.get("bedrooms")),
        "bathrooms": _int(details.get("bathrooms")),
        "built_up_area": _float(details.get("built_up_area")),
        "more_features": [],
        "media": _media_for_details(payload, property_media_rows=_load_property_media(db, property_id)),
        "latitude": listing["location_detail"]["latitude"],
        "longitude": listing["location_detail"]["longitude"],
        "location_name": ", ".join(part for part in [listing["areaName"], listing["city"]] if part) or None,
        "general": {
            "floor_type": None,
            "floor_number": None,
            "building_status": details.get("completion_status"),
            "built_in_year": None,
            "furniture_status": None,
            "furniture_condition": None,
            "garage_type": None,
            "total_floors_in_building": _int(details.get("total_floors")) or None,
        },
        "details": {
            "built_up_area": _float(details.get("built_up_area")),
            "land_area": None,
            "garden_area": None,
            "terrace_area": None,
            "area_unit": settings.default_measurement_unit,
            "bedrooms": _int(details.get("bedrooms")),
            "master_bedrooms": None,
            "bathrooms": _int(details.get("bathrooms")),
            "living_rooms": None,
            "salons": None,
            "balconies": None,
            "entrances": None,
            "kitchens": None,
            "kitchen_type": None,
            "maid_rooms": None,
            "driver_rooms": None,
            "store_rooms": None,
        },
        "features": {"amenities": [str(item) for item in _feature_ids(payload)]},
        "features_list": _feature_list(db, payload),
        "pricing": {
            "listing_type": listing_type,
            "selling_price": _float(pricing.get("price")),
            "currency": pricing.get("currency") or settings.default_currency,
            "service_charge": _float(pricing.get("service_charge")),
            "maintenance_fee": _float(pricing.get("maintenance_fee")),
            "price_on_request": False,
            "rent_commission_percent": None,
            "contract_duration": None,
            "payment_method": pricing.get("payment_method"),
            "is_negotiable": False,
            "installment_available": False,
        },
        "created_at": iso(submission.created_at),
        "updated_at": iso(submission.updated_at),
        "published_at": iso(submission.reviewed_at),
        "expires_at": None,
        "sold_at": None,
        "rented_at": None,
        "created_by": {
            "id": 1,
            "name": submitter.full_name if submitter else "",
            "role": "agent",
        },
    }
    if is_authenticated:
        detail["agency"] = _agency_payload(agency)
        detail["guard_name"] = details.get("guard_name")
        detail["guard_number"] = details.get("guard_number")
        detail["guard_phone_number"] = details.get("guard_phone_number")
        detail["details"]["guard_name"] = details.get("guard_name")
        detail["details"]["guard_number"] = details.get("guard_number")
        detail["details"]["guard_phone_number"] = details.get("guard_phone_number")
    detail.pop("owner", None)
    if not is_authenticated:
        detail = _strip_anonymous_property_detail_fields(detail)
    if agent is not None:
        detail["agent"] = agent
    else:
        detail.pop("agent", None)
    # Location tab: show_location=true exposes location to every role, including anonymous.
    # show_location=false keeps the current location payload on the detail response.
    show_location = bool(listing.get("show_location"))
    detail["show_location"] = show_location
    if show_location:
        detail["location"] = listing["location"]
        detail["location_detail"] = listing["location_detail"]
        detail["latitude"] = listing["location_detail"]["latitude"]
        detail["longitude"] = listing["location_detail"]["longitude"]
    return detail


def list_public_submissions(db: Session) -> list[tuple[PropertyListingSubmission, User | None]]:
    rows = db.execute(
        select(PropertyListingSubmission, User)
        .join(User, User.id == PropertyListingSubmission.submitted_by)
        .where(
            PropertyListingSubmission.deleted_at.is_(None),
            PropertyListingSubmission.property_id.is_not(None),
            PropertyListingSubmission.status.in_(PUBLIC_STATUSES),
        )
        .order_by(PropertyListingSubmission.updated_at.desc())
    ).all()
    latest_by_property: dict[UUID, tuple[PropertyListingSubmission, User | None]] = {}
    for submission, user in rows:
        property_id = submission.property_id or submission.id
        if is_property_deal_closed(db, property_id):
            continue
        if property_id not in latest_by_property:
            latest_by_property[property_id] = (submission, user)
    return list(latest_by_property.values())


def is_property_deal_closed(db: Session, property_id: UUID) -> bool:
    return bool(
        db.execute(
            select(PropertyDealClosure.id).where(
                PropertyDealClosure.property_id == property_id,
                PropertyDealClosure.status == DEAL_CLOSED_STATUS,
            )
        ).first()
    )


def find_public_submission_by_hash(db: Session, property_key: str | int) -> tuple[PropertyListingSubmission, User | None] | None:
    key = str(property_key)
    try:
        uuid_key = UUID(key)
    except ValueError:
        uuid_key = None

    rows = list_public_submissions(db)
    for submission, user in rows:
        property_id = submission.property_id or submission.id
        if uuid_key and property_id == uuid_key:
            return submission, user
        if str(stable_property_hash(property_id)) == key:
            return submission, user
    return None


def find_submission_by_hash(db: Session, property_key: str | int) -> tuple[PropertyListingSubmission, User | None] | None:
    key = str(property_key)
    try:
        uuid_key = UUID(key)
    except ValueError:
        uuid_key = None

    rows = db.execute(
        select(PropertyListingSubmission, User)
        .join(User, User.id == PropertyListingSubmission.submitted_by)
        .where(PropertyListingSubmission.deleted_at.is_(None))
        .order_by(PropertyListingSubmission.updated_at.desc())
    ).all()
    for submission, user in rows:
        property_id = submission.property_id or submission.id
        if uuid_key and (property_id == uuid_key or submission.id == uuid_key):
            return submission, user
        if str(stable_property_hash(property_id)) == key:
            return submission, user
    return None


def get_public_submission_or_404(db: Session, property_key: str | int) -> tuple[PropertyListingSubmission, User | None]:
    match = find_public_submission_by_hash(db, property_key)
    if not match:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Property not found")
    return match


def get_visible_submission_or_404(
    db: Session,
    property_key: str | int,
    *,
    user_id: UUID | None = None,
    roles: tuple[str, ...] = (),
    agency_id: UUID | None = None,
) -> tuple[PropertyListingSubmission, User | None]:
    match = find_submission_by_hash(db, property_key)
    if user_id is None:
        public_match = find_public_submission_by_hash(db, property_key)
        if public_match:
            return public_match
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Property not found")

    if match:
        submission, user = match
        if can_view_submission(
            db,
            submission,
            user_id=user_id,
            roles=roles,
            agency_id=agency_id,
        ):
            return submission, user

    public_match = find_public_submission_by_hash(db, property_key)
    if public_match:
        return public_match

    raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Property not found")


def resolve_property_uuid_or_404(db: Session, property_key: str | int) -> UUID:
    submission, _ = get_public_submission_or_404(db, property_key)
    return submission.property_id or submission.id


def favorite_lookup(db: Session, user_id: UUID) -> dict[UUID, UserPropertyFavorite]:
    rows = db.execute(select(UserPropertyFavorite).where(UserPropertyFavorite.user_id == user_id)).scalars().all()
    return {row.property_id: row for row in rows}


def apply_public_filters(
    rows: list[tuple[PropertyListingSubmission, User | None]],
    *,
    category: str | None = None,
    status: str | None = None,
    type: str | None = None,
    city: str | None = None,
    locations: str | None = None,
    budgetMin: float | None = None,
    budgetMax: float | None = None,
    bedrooms: int | None = None,
    rooms: int | None = None,
    bathrooms: int | None = None,
    parking: int | None = None,
    propertyAge: str | None = None,
    floorLevel: str | None = None,
    furnitureStatus: str | None = None,
    minArea: float | None = None,
    maxArea: float | None = None,
    minPlotArea: float | None = None,
    maxPlotArea: float | None = None,
    governorate: str | None = None,
    directorate: str | None = None,
    village: str | None = None,
    parcelName: str | None = None,
    amenities: str | None = None,
    similar_to: str | None = None,
    db: Session,
) -> list[tuple[PropertyListingSubmission, User | None]]:
    categories, types, cities, areas = _taxonomy_maps(db)
    required_features = {_int(value) for value in (amenities or "").replace("|", ",").split(",") if _int(value)}
    similar_match = find_public_submission_by_hash(db, similar_to) if similar_to else None
    if similar_to and not similar_match:
        return []
    similar_payload = similar_match[0].payload if similar_match else None
    similar_basic = (similar_payload or {}).get("basic_information") or {}

    filtered = []
    for submission, user in rows:
        payload = submission.payload or {}
        basic = payload.get("basic_information") or {}
        location = payload.get("location") or {}
        details = payload.get("property_details") or {}
        pricing = payload.get("pricing") or {}
        category_obj = categories.get(_int(basic.get("category_id")))
        type_obj = types.get(_int(basic.get("type_id")))
        city_obj = cities.get(_int(location.get("city_id")))
        area_obj = areas.get(_int(location.get("area_id")))

        if category and category_obj and _slug(category_obj.slug) != _slug(category):
            continue
        if type and type_obj and _slug(type_obj.slug) != _slug(type):
            continue
        if status:
            purpose = "rent" if basic.get("listing_purpose") == "rent" else "buy"
            if _slug(status) not in {_slug(purpose), _slug(basic.get("listing_purpose"))}:
                continue
        if city and city_obj and _slug(city_obj.name) != _slug(city):
            continue
        if locations and area_obj and _slug(area_obj.name) != _slug(locations):
            continue
        price = _float(pricing.get("price")) or 0
        if budgetMin is not None and price < budgetMin:
            continue
        if budgetMax is not None and price > budgetMax:
            continue
        if bedrooms is not None and _int(details.get("bedrooms")) < bedrooms:
            continue
        if rooms is not None and _int(details.get("bedrooms")) < rooms:
            continue
        if bathrooms is not None and _int(details.get("bathrooms")) < bathrooms:
            continue
        if parking is not None and _int(details.get("parking_spaces")) < parking:
            continue
        if propertyAge and _token(details.get("property_age")) != _token(propertyAge):
            continue
        if floorLevel and _token(details.get("floor_level") or details.get("floor_number")) != _token(floorLevel):
            continue
        if furnitureStatus and _token(details.get("furniture_status")) != _token(furnitureStatus):
            continue
        area_value = _float(details.get("built_up_area")) or 0
        if minArea is not None and area_value < minArea:
            continue
        if maxArea is not None and area_value > maxArea:
            continue
        plot_area_value = (
            _float(details.get("land_area"))
            or _float(details.get("plot_area"))
            or (area_value if _token(category_obj.slug if category_obj else category) == "land" else 0)
        )
        if minPlotArea is not None and plot_area_value < minPlotArea:
            continue
        if maxPlotArea is not None and plot_area_value > maxPlotArea:
            continue
        if governorate and not _text_match(location.get("governorate") or location.get("state"), governorate):
            continue
        if directorate and not _text_match(location.get("directorate") or location.get("district"), directorate):
            continue
        if village and not _text_match(location.get("village"), village):
            continue
        if parcelName and not _text_match(location.get("parcel_name") or details.get("parcel_name"), parcelName):
            continue
        if required_features and not required_features.issubset(set(_feature_ids(payload))):
            continue
        if similar_payload and submission.id != similar_match[0].id:
            if basic.get("category_id") != similar_basic.get("category_id"):
                continue
        elif similar_payload:
            continue
        filtered.append((submission, user))
    return filtered


def sort_public_rows(rows: list[tuple[PropertyListingSubmission, User | None]], sort: str | None) -> list[tuple[PropertyListingSubmission, User | None]]:
    normalized_sort = (sort or "").replace("_", "-")
    if normalized_sort == "price-asc":
        return sorted(rows, key=lambda row: _float(((row[0].payload or {}).get("pricing") or {}).get("price")) or 0)
    if normalized_sort == "price-desc":
        return sorted(rows, key=lambda row: _float(((row[0].payload or {}).get("pricing") or {}).get("price")) or 0, reverse=True)
    return sorted(rows, key=lambda row: row[0].updated_at or row[0].created_at, reverse=True)


def serialize_feature_catalog_item(db: Session, feature: Feature) -> dict[str, Any]:
    category = db.get(PropertyCategory, feature.category_id) if feature.category_id else None
    property_type = db.get(PropertyType, feature.property_type_id) if feature.property_type_id else None
    return {
        "id": feature.id,
        "name": feature.name,
        "slug": feature.slug,
        "category_id": feature.category_id,
        "property_type_id": feature.property_type_id,
        "feature_group": feature.feature_group,
        "display_order": feature.display_order,
        "is_active": bool(feature.is_active),
        "created_at": iso(feature.created_at),
        "updated_at": iso(feature.updated_at),
        "category": {"id": category.id, "name": category.name, "slug": category.slug} if category else None,
        "property_type": {
            "id": property_type.id,
            "category_id": property_type.category_id,
            "name": property_type.name,
            "slug": property_type.slug,
        }
        if property_type
        else None,
    }
