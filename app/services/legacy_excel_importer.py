"""Import legacy Abdoun Excel property data into property_listing_submissions."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.live_schema import (
    AgencyMaster,
    Area,
    City,
    PropertyCategory,
    PropertyListingSubmission,
    PropertyType,
    User,
)
from app.services.auth import assign_role, normalize_username
from app.services.property_submissions import compute_step_completion, sync_property_media_from_payload
from app.services.user_agencies import REL_PROPERTY_OWNER, ensure_user_agency_mapping

SOURCE_NAME = "legacy-excel-import"


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")


def _clean(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    return text


def _uuid(value: Any) -> UUID | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return UUID(text)
    except ValueError:
        return None


def _int(value: Any, default: int | None = None) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return default


def _float(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        parsed = float(value)
        if pd.isna(parsed):
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def _load_taxonomy(db: Session) -> tuple[dict[str, PropertyCategory], list[PropertyType], list[City], list[Area]]:
    categories = {category.slug: category for category in db.execute(select(PropertyCategory)).scalars().all()}
    types = db.execute(select(PropertyType)).scalars().all()
    cities = db.execute(select(City)).scalars().all()
    areas = db.execute(select(Area)).scalars().all()
    return categories, types, cities, areas


def _match_category(categories: dict[str, PropertyCategory], slug: str) -> PropertyCategory:
    if slug in categories:
        return categories[slug]
    return next(iter(categories.values()))


def _match_type(types: list[PropertyType], category_id: int, slug: str) -> PropertyType:
    for property_type in types:
        if property_type.category_id == category_id and property_type.slug == slug:
            return property_type
    for property_type in types:
        if property_type.category_id == category_id and _slug(property_type.name) == _slug(slug):
            return property_type
    fallback = {"residential": "apartments", "commercial": "offices", "land": "residential-lands"}
    category_slug = next((category.slug for category in categories_by_id.values() if category.id == category_id), "")
    fallback_slug = fallback.get(category_slug, "apartments")
    for property_type in types:
        if property_type.category_id == category_id and property_type.slug == fallback_slug:
            return property_type
    return next(property_type for property_type in types if property_type.category_id == category_id)


categories_by_id: dict[int, PropertyCategory] = {}


def _match_city(cities: list[City], name: str | None) -> City:
    target = _slug(name)
    for city in cities:
        if _slug(city.name) == target:
            return city
    for city in cities:
        if target and target in _slug(city.name):
            return city
    return cities[0]


def _match_area(areas: list[Area], city_id: int, name: str | None) -> Area:
    city_areas = [area for area in areas if area.city_id == city_id]
    target = _slug(name)
    for area in city_areas:
        if _slug(area.name) == target:
            return area
    for area in city_areas:
        if target and target in _slug(area.name):
            return area
    return city_areas[0] if city_areas else areas[0]


def _resolve_listing_purpose(raw: str | None) -> str:
    value = (raw or "sale").strip().lower()
    if value in {"rent", "sale"}:
        return value
    return "sale"


def _resolve_status(raw: str | None) -> str:
    value = (raw or "active").strip().lower()
    if value in {"active", "deal-closed", "deactivated", "draft"}:
        return value
    return "active"


def _build_payload(
    row: pd.Series,
    *,
    category: PropertyCategory,
    property_type: PropertyType,
    city: City,
    area: Area,
    owner: dict[str, Any],
) -> dict[str, Any]:
    listing_purpose = _resolve_listing_purpose(_clean(row.get("listing_purpose")))
    price = _clean(row.get("price")) or _clean(row.get("sale_price")) or _clean(row.get("rent_price")) or "0"
    export_ref = _clean(row.get("export_reference")) or ""

    images: list[dict[str, Any]] = []
    media_url = _clean(row.get("media_url"))
    if media_url:
        images.append({"url": media_url, "is_primary": True, "display_order": 0})

    return {
        "_seed": {
            "source": SOURCE_NAME,
            "source_id": export_ref,
            "seeded_at": datetime.now(timezone.utc).isoformat(),
        },
        "basic_information": {
            "category_id": category.id,
            "type_id": property_type.id,
            "listing_purpose": listing_purpose,
            "title": _clean(row.get("title")) or "Legacy property",
            "description": _clean(row.get("description")),
            "is_exclusive": False,
        },
        "location": {
            "country_id": 1,
            "city_id": city.id,
            "area_id": area.id,
            "address": _clean(row.get("address")) or (area.name if area else city.name),
            "latitude": _float(row.get("latitude")),
            "longitude": _float(row.get("longitude")),
        },
        "owner_information": {
            "owners": [
                {
                    "id": owner.get("id") or "legacy-owner",
                    "full_name": owner.get("full_name") or "Legacy Property Owner",
                    "email": owner.get("email"),
                    "phone": owner.get("phone"),
                    "nationality": None,
                    "ssi": None,
                    "address": None,
                    "documents": [],
                }
            ]
        },
        "property_details": {
            "reference_number": export_ref,
            "bedrooms": _int(row.get("bedrooms")),
            "bathrooms": _int(row.get("bathrooms")),
            "built_up_area": _int(row.get("built_up_area_sqm")),
            "land_area": _int(row.get("land_area_sqm")),
            "floor_number": _int(row.get("floor_number")),
            "total_floors": _int(row.get("total_floors")),
            "construction_year": _int(row.get("construction_year")),
            "furnishing": _clean(row.get("furnishing")),
            "finishing": _clean(row.get("finishing")),
            "parking": _clean(row.get("parking")),
            "heating": _clean(row.get("heating")),
            "view": _clean(row.get("view")),
            "features_amenities": _clean(row.get("features_amenities")),
        },
        "pricing": {
            "price": price,
            "currency": _clean(row.get("currency")) or "JOD",
            "payment_method": None,
        },
        "amenities": {"feature_ids": []},
        "media_documents": {"images": images, "documents": [], "youtube_url": None, "virtual_tour_url": None},
        "review_submit": {
            "terms_accepted": True,
            "privacy_accepted": True,
            "public_display_authorized": True,
            "fees_acknowledged": True,
        },
    }


def _get_or_create_owner_user(
    db: Session,
    *,
    owner_row: pd.Series | None,
    agency_id: UUID,
    actor_user_id: UUID,
    cache: dict[str, User],
) -> User | None:
    if owner_row is None:
        return None

    owner_user_id = _uuid(owner_row.get("owner_user_id"))
    email = _clean(owner_row.get("email"))
    cache_key = str(owner_user_id) if owner_user_id else (normalize_username(email) if email else None)
    if cache_key and cache_key in cache:
        return cache[cache_key]

    user: User | None = None
    if owner_user_id:
        user = db.get(User, owner_user_id)
    if user is None and email:
        user = db.execute(select(User).where(User.email == normalize_username(email))).scalar_one_or_none()
    if user is None:
        if not owner_user_id:
            return None
        user = User(
            id=owner_user_id,
            full_name=_clean(owner_row.get("full_name")) or "Legacy Property Owner",
            email=normalize_username(email or f"legacy-owner-{str(owner_user_id)[:8]}@import.local"),
            phone_number=_clean(owner_row.get("phone_number")),
            is_active=True,
            is_email_verified=False,
            is_phone_verified=False,
            preferred_language=_clean(owner_row.get("preferred_language")) or "ar",
            agency_id=agency_id,
        )
        db.add(user)
        db.flush()
        assign_role(db, user.id, "owner", assigned_by=actor_user_id)

    ensure_user_agency_mapping(
        db,
        user_id=user.id,
        agency_id=agency_id,
        relationship_type=REL_PROPERTY_OWNER,
        actor_user_id=actor_user_id,
    )
    assign_role(db, user.id, "owner", assigned_by=actor_user_id)

    if cache_key:
        cache[cache_key] = user
    return user


def _existing_seed_ids(db: Session) -> set[str]:
    rows = db.execute(select(PropertyListingSubmission)).scalars().all()
    existing: set[str] = set()
    for row in rows:
        if not isinstance(row.payload, dict):
            continue
        seed = row.payload.get("_seed") or {}
        if seed.get("source") == SOURCE_NAME and seed.get("source_id"):
            existing.add(str(seed["source_id"]))
    return existing


def import_legacy_excel(
    db: Session,
    *,
    properties_df: pd.DataFrame,
    owners_df: pd.DataFrame | None,
    submitter: User,
    agency_id: UUID,
    dry_run: bool = False,
    limit: int | None = None,
    skip_owners: bool = False,
    media_df: pd.DataFrame | None = None,
    media_base_url: str | None = None,
) -> dict[str, Any]:
    global categories_by_id
    categories, types, cities, areas = _load_taxonomy(db)
    categories_by_id = {category.id: category for category in categories.values()}

    owners_by_id = {}
    if owners_df is not None and not owners_df.empty:
        for _, owner_row in owners_df.iterrows():
            owner_id = _clean(owner_row.get("owner_user_id"))
            if owner_id:
                owners_by_id[owner_id] = owner_row

    media_by_property: dict[str, list[dict[str, Any]]] = {}
    if media_df is not None and not media_df.empty:
        for _, media_row in media_df.iterrows():
            property_id = _clean(media_row.get("property_id"))
            if not property_id:
                continue
            url = _clean(media_row.get("url"))
            file_name = _clean(media_row.get("file_name"))
            if not url and media_base_url and file_name:
                url = f"{media_base_url.rstrip('/')}/{file_name.lstrip('/')}"
            if not url:
                continue
            media_by_property.setdefault(property_id, []).append(
                {
                    "url": url,
                    "file_name": file_name,
                    "display_order": _int(media_row.get("display_order"), 0) or 0,
                    "is_primary": bool(media_row.get("is_primary")),
                }
            )

    existing_seed_ids = _existing_seed_ids(db)
    owner_cache: dict[str, User] = {}
    planned_owner_ids: set[str] = set()
    planned: list[dict[str, Any]] = []
    skipped_existing = 0
    skipped_invalid = 0

    rows = properties_df.head(limit) if limit else properties_df
    for _, row in rows.iterrows():
        export_ref = _clean(row.get("export_reference"))
        if not export_ref:
            skipped_invalid += 1
            continue
        if export_ref in existing_seed_ids:
            skipped_existing += 1
            continue

        property_id = _uuid(row.get("property_id"))
        if property_id is None:
            skipped_invalid += 1
            continue

        category = _match_category(categories, _clean(row.get("category_slug")) or "residential")
        property_type = _match_type(types, category.id, _clean(row.get("type_slug")) or "apartments")
        city = _match_city(cities, _clean(row.get("city_name_en")))
        area = _match_area(areas, city.id, _clean(row.get("area_name")))

        owner_user: User | None = None
        owner_payload = {
            "id": "legacy-owner",
            "full_name": _clean(row.get("owner_full_name")) or "Legacy Property Owner",
            "email": _clean(row.get("owner_email")),
            "phone": _clean(row.get("owner_phone")),
        }
        owner_user_id_text = _clean(row.get("owner_user_id"))
        if not skip_owners and owner_user_id_text:
            owner_payload["id"] = owner_user_id_text
            if not dry_run:
                owner_row = owners_by_id.get(owner_user_id_text)
                owner_user = _get_or_create_owner_user(
                    db,
                    owner_row=owner_row,
                    agency_id=agency_id,
                    actor_user_id=submitter.id,
                    cache=owner_cache,
                )
                if owner_user:
                    owner_payload = {
                        "id": str(owner_user.id),
                        "full_name": owner_user.full_name,
                        "email": owner_user.email,
                        "phone": owner_user.phone_number,
                    }
            elif owner_user_id_text not in planned_owner_ids:
                planned_owner_ids.add(owner_user_id_text)

        payload = _build_payload(
            row,
            category=category,
            property_type=property_type,
            city=city,
            area=area,
            owner=owner_payload,
        )

        property_key = str(property_id)
        extra_images = media_by_property.get(property_key) or []
        if extra_images:
            payload["media_documents"]["images"] = sorted(
                extra_images,
                key=lambda item: item.get("display_order", 0),
            )

        status = _resolve_status(_clean(row.get("status")))
        submitted_by = owner_user.id if owner_user else submitter.id
        if dry_run and owner_user_id_text and not skip_owners:
            submitted_by = UUID(owner_user_id_text)

        planned.append(
            {
                "export_reference": export_ref,
                "property_id": property_id,
                "submitted_by": submitted_by,
                "status": status,
                "payload": payload,
            }
        )

    if dry_run:
        return {
            "dry_run": True,
            "planned_inserts": len(planned),
            "skipped_existing": skipped_existing,
            "skipped_invalid": skipped_invalid,
            "owners_created_or_linked": len(owner_cache) if not dry_run else len(planned_owner_ids),
            "preview": [
                {
                    "export_reference": item["export_reference"],
                    "property_id": str(item["property_id"]),
                    "status": item["status"],
                    "title": item["payload"]["basic_information"]["title"],
                    "category_id": item["payload"]["basic_information"]["category_id"],
                    "type_id": item["payload"]["basic_information"]["type_id"],
                    "images": len(item["payload"]["media_documents"]["images"]),
                }
                for item in planned[:15]
            ],
        }

    inserted = 0
    now = datetime.now(timezone.utc)
    for item in planned:
        payload = item["payload"]
        submission = PropertyListingSubmission(
            submitted_by=item["submitted_by"],
            agency_id=agency_id,
            property_id=item["property_id"],
            status=item["status"],
            current_step=8,
            last_completed_step=8,
            payload=payload,
            step_completion=compute_step_completion(payload),
            terms_accepted=True,
            privacy_accepted=True,
            public_display_authorized=True,
            fees_acknowledged=True,
            submitted_at=now,
            reviewed_by=submitter.id if item["status"] == "active" else None,
            reviewed_at=now if item["status"] == "active" else None,
            review_reason="Imported from legacy Excel backup.",
        )
        db.add(submission)
        if payload["media_documents"]["images"]:
            sync_property_media_from_payload(db, property_id=item["property_id"], payload=payload)
        inserted += 1

    db.commit()
    return {
        "dry_run": False,
        "inserted": inserted,
        "skipped_existing": skipped_existing,
        "skipped_invalid": skipped_invalid,
        "owners_created_or_linked": len(owner_cache),
        "submitter": submitter.email,
        "agency_id": str(agency_id),
    }
