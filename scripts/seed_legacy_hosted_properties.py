from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid5

import requests
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.models.live_schema import (
    Area,
    City,
    PropertyCategory,
    PropertyListingSubmission,
    PropertyType,
    User,
)
from app.services.property_submissions import compute_step_completion


SOURCE_NAME = "legacy-hosted-dev-api"
SOURCE_API_BASE = "https://dev-api-abdn.wpsitedesigner.com/api/v1"
SOURCE_NAMESPACE = UUID("c8a8ed67-f7c3-4d32-9cb9-ec86fc45bf69")
DEFAULT_PAGE_SIZE = 50
MAX_IMAGES_PER_PROPERTY = 8

SEED_TARGETS = [
    {
        "key": "residential-buy-villa",
        "category": "residential",
        "status": "buy",
        "type": "villa",
        "limit": 12,
    },
    {
        "key": "residential-buy-apartment",
        "category": "residential",
        "status": "buy",
        "type": "apartment",
        "limit": 12,
    },
    {
        "key": "residential-rent-villa",
        "category": "residential",
        "status": "rent",
        "type": "villa",
        "limit": 12,
    },
    {
        "key": "residential-rent-apartment",
        "category": "residential",
        "status": "rent",
        "type": "apartment",
        "limit": 12,
    },
    {
        "key": "commercial-buy",
        "category": "commercial",
        "status": "buy",
        "type": None,
        "limit": 6,
    },
    {
        "key": "commercial-rent",
        "category": "commercial",
        "status": "rent",
        "type": None,
        "limit": 4,
    },
    {
        "key": "land-buy",
        "category": "land",
        "status": "buy",
        "type": None,
        "limit": 8,
    },
]


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("en") or value.get("ar") or value.get("fr") or value.get("esp") or "")
    return str(value or "")


def _nullable_text(value: Any) -> str | None:
    text = _text(value).strip()
    return text or None


def _int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return default


def _price(value: Any) -> str:
    match = re.search(r"[\d,]+(?:\.\d+)?", str(value or ""))
    return match.group(0).replace(",", "") if match else "0"


def _strip_query(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _filename_from_url(url: str | None) -> str | None:
    if not url:
        return None
    return urlsplit(url).path.rsplit("/", 1)[-1] or None


def _fetch_items(target: dict[str, Any], max_pages: int) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "page": 1,
        "pageSize": DEFAULT_PAGE_SIZE,
        "category": target["category"],
        "status": target["status"],
        "sort": "newest",
    }
    if target.get("type"):
        params["type"] = target["type"]

    collected: list[dict[str, Any]] = []
    seen: set[str] = set()

    for page in range(1, max_pages + 1):
        params["page"] = page
        response = requests.get(f"{SOURCE_API_BASE}/properties", params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        items = ((payload.get("data") or {}).get("items") or [])

        if not items:
            break

        for item in items:
            source_id = str(item.get("property_id") or item.get("id") or "")
            if not source_id or source_id in seen:
                continue
            seen.add(source_id)
            item["_seed_target"] = target["key"]
            item["_seed_category"] = target["category"]
            item["_seed_status"] = target["status"]
            collected.append(item)

        if len(collected) >= target["limit"] * 3:
            break

    with_media = [item for item in collected if ((item.get("media") or {}).get("images") or [])]
    without_media = [item for item in collected if item not in with_media]
    return (with_media + without_media)[: target["limit"]]


def _match_category(categories: dict[str, PropertyCategory], slug: str) -> PropertyCategory:
    return categories[slug]


def _match_type(types: list[PropertyType], category_id: int, item: dict[str, Any]) -> PropertyType:
    candidates = [item.get("searchPropertyType"), item.get("propertyType")]
    candidate_slugs = {_slug(value) for value in candidates if value}
    alias = {
        "villas": "villa",
        "apartments": "apartment",
        "lot-land-for-sale": "land",
        "lot-land": "land",
    }
    candidate_slugs |= {alias[slug] for slug in list(candidate_slugs) if slug in alias}

    for property_type in types:
        if property_type.category_id == category_id and property_type.slug in candidate_slugs:
            return property_type

    normalized_names = {_slug(property_type.name): property_type for property_type in types if property_type.category_id == category_id}
    for slug in candidate_slugs:
        if slug in normalized_names:
            return normalized_names[slug]

    fallback_by_category = {
        "residential": "apartment",
        "commercial": "office",
        "land": "land",
    }
    category_slug = next((category.slug for category in categories_by_id.values() if category.id == category_id), "")
    fallback_slug = fallback_by_category.get(category_slug)
    for property_type in types:
        if property_type.category_id == category_id and property_type.slug == fallback_slug:
            return property_type

    return next(property_type for property_type in types if property_type.category_id == category_id)


categories_by_id: dict[int, PropertyCategory] = {}


def _match_city(cities: list[City], item: dict[str, Any]) -> City:
    city_name = _slug(item.get("city") or ((item.get("location") or {}).get("city")))
    for city in cities:
        if _slug(city.name) == city_name:
            return city
    return cities[0]


def _match_area(areas: list[Area], city_id: int, item: dict[str, Any]) -> Area:
    area_name = _slug(item.get("areaName") or ((item.get("location") or {}).get("region")))
    city_areas = [area for area in areas if area.city_id == city_id]
    for area in city_areas:
        if _slug(area.name) == area_name:
            return area
    return city_areas[0] if city_areas else areas[0]


def _media_images(item: dict[str, Any]) -> list[dict[str, Any]]:
    images = []
    for index, image in enumerate(((item.get("media") or {}).get("images") or [])[:MAX_IMAGES_PER_PROPERTY]):
        if isinstance(image, str):
            url = _strip_query(image)
        else:
            url = _strip_query(image.get("url") or image.get("thumb_url"))
        if not url:
            continue
        images.append(
            {
                "url": url,
                "file_name": _filename_from_url(url),
                "display_order": index,
                "is_primary": index == 0,
            }
        )
    return images


def _owner_payload(item: dict[str, Any]) -> dict[str, Any]:
    owners = item.get("owners") or []
    if owners:
        return {
            "owners": [
                {
                    "id": owner.get("owner_id") or str(index + 1),
                    "full_name": owner.get("full_name") or "Legacy Property Owner",
                    "email": owner.get("email"),
                    "phone": owner.get("phone"),
                    "nationality": owner.get("nationality"),
                    "ssi": owner.get("ssi"),
                    "address": owner.get("address"),
                    "documents": owner.get("documents") or [],
                }
                for index, owner in enumerate(owners)
            ]
        }
    return {
        "owners": [
            {
                "id": "legacy-owner",
                "full_name": "Legacy Property Owner",
                "email": None,
                "phone": None,
                "nationality": None,
                "ssi": None,
                "address": None,
                "documents": [],
            }
        ]
    }


def _submission_payload(
    item: dict[str, Any],
    *,
    category: PropertyCategory,
    property_type: PropertyType,
    city: City,
    area: Area,
) -> dict[str, Any]:
    source_id = str(item.get("property_id") or item.get("id"))
    listing_purpose = "rent" if item.get("_seed_status") == "rent" else "sale"
    address = _text(((item.get("location_detail") or item.get("location") or {}).get("address"))).strip()
    title = _text(item.get("title")).strip() or "Legacy property"
    description = _nullable_text(item.get("description")) or item.get("highlights") or title

    return {
        "_seed": {
            "source": SOURCE_NAME,
            "source_id": source_id,
            "source_target": item.get("_seed_target"),
            "seeded_at": datetime.now(timezone.utc).isoformat(),
        },
        "basic_information": {
            "category_id": category.id,
            "type_id": property_type.id,
            "listing_purpose": listing_purpose,
            "title": title,
            "description": description,
            "is_exclusive": bool(item.get("is_exclusive")),
        },
        "location": {
            "country_id": 1,
            "city_id": city.id,
            "area_id": area.id,
            "address": address or area.name,
        },
        "owner_information": _owner_payload(item),
        "property_details": {
            "reference_number": item.get("reference_number") or source_id[:8],
            "bedrooms": _int(item.get("beds")),
            "bathrooms": _int(item.get("baths")),
            "built_up_area": _int(item.get("area")),
            "total_floors": None,
            "completion_status": item.get("handover"),
        },
        "pricing": {
            "price": _price(item.get("price")),
            "currency": "JOD",
            "payment_method": item.get("paymentPlan"),
        },
        "amenities": {"feature_ids": []},
        "media_documents": {
            "images": _media_images(item),
            "documents": [],
            "youtube_url": None,
            "virtual_tour_url": (item.get("media") or {}).get("virtual_tour_url"),
        },
        "review_submit": {
            "terms_accepted": True,
            "privacy_accepted": True,
            "public_display_authorized": True,
            "fees_acknowledged": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed current DB from hosted legacy development property API.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-pages", type=int, default=5)
    parser.add_argument("--submitter-email", default="amondal@coderlook.com")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        categories = {category.slug: category for category in db.execute(select(PropertyCategory)).scalars().all()}
        global categories_by_id
        categories_by_id = {category.id: category for category in categories.values()}
        types = db.execute(select(PropertyType)).scalars().all()
        cities = db.execute(select(City)).scalars().all()
        areas = db.execute(select(Area)).scalars().all()
        submitter = db.execute(select(User).where(User.email == args.submitter_email)).scalar_one_or_none()
        if submitter is None:
            submitter = db.execute(select(User).order_by(User.created_at)).scalars().first()
        if submitter is None:
            raise RuntimeError("No user exists to use as seeded property submitter.")

        existing_by_property_id = {
            str(row.property_id): row
            for row in db.execute(select(PropertyListingSubmission)).scalars().all()
            if row.property_id
        }
        existing_seed_ids = {
            str(row.payload.get("_seed", {}).get("source_id"))
            for row in db.execute(select(PropertyListingSubmission)).scalars().all()
            if isinstance(row.payload, dict) and row.payload.get("_seed", {}).get("source") == SOURCE_NAME
        }

        fetched: list[dict[str, Any]] = []
        for target in SEED_TARGETS:
            fetched.extend(_fetch_items(target, args.max_pages))

        planned_inserts: list[tuple[dict[str, Any], dict[str, Any]]] = []
        planned_updates: list[tuple[PropertyListingSubmission, dict[str, Any], dict[str, Any]]] = []
        skipped_existing_active = 0
        skipped_existing_seed = 0
        for item in fetched:
            source_id = str(item.get("property_id") or item.get("id"))
            if source_id in existing_seed_ids:
                skipped_existing_seed += 1
                continue
            category = _match_category(categories, item["_seed_category"])
            property_type = _match_type(types, category.id, item)
            city = _match_city(cities, item)
            area = _match_area(areas, city.id, item)
            payload = _submission_payload(
                item,
                category=category,
                property_type=property_type,
                city=city,
                area=area,
            )
            existing = existing_by_property_id.get(source_id)
            if existing is not None:
                if existing.status == "active":
                    skipped_existing_active += 1
                    continue
                planned_updates.append((existing, item, payload))
                continue

            planned_inserts.append((item, payload))

        summary: dict[str, Any] = {
            "fetched": len(fetched),
            "skipped_existing_active": skipped_existing_active,
            "skipped_existing_seed": skipped_existing_seed,
            "planned_inserts": len(planned_inserts),
            "planned_updates": len(planned_updates),
            "planned_total": len(planned_inserts) + len(planned_updates),
            "by_target": {},
            "with_media": sum(
                1
                for _, payload in planned_inserts
                if payload["media_documents"]["images"]
            )
            + sum(
                1
                for _, _, payload in planned_updates
                if payload["media_documents"]["images"]
            ),
        }
        for item, payload in planned_inserts:
            target = item["_seed_target"]
            summary["by_target"][target] = summary["by_target"].get(target, 0) + 1
        for _, item, payload in planned_updates:
            target = item["_seed_target"]
            summary["by_target"][target] = summary["by_target"].get(target, 0) + 1

        print(summary)

        if args.dry_run:
            preview = [
                ("insert", None, item, payload)
                for item, payload in planned_inserts
            ] + [
                ("update", row.status, item, payload)
                for row, item, payload in planned_updates
            ]
            for action, previous_status, item, payload in preview[:15]:
                print(
                    {
                        "action": action,
                        "previous_status": previous_status,
                        "source_id": str(item.get("property_id") or item.get("id")),
                        "target": item["_seed_target"],
                        "title": payload["basic_information"]["title"],
                        "category_id": payload["basic_information"]["category_id"],
                        "type_id": payload["basic_information"]["type_id"],
                        "purpose": payload["basic_information"]["listing_purpose"],
                        "images": len(payload["media_documents"]["images"]),
                    }
                )
            return

        now = datetime.now(timezone.utc)
        for item, payload in planned_inserts:
            source_id = str(item.get("property_id") or item.get("id"))
            property_id = uuid5(SOURCE_NAMESPACE, source_id)
            submission = PropertyListingSubmission(
                submitted_by=submitter.id,
                property_id=property_id,
                status="active",
                current_step=7,
                last_completed_step=7,
                payload=payload,
                step_completion=compute_step_completion(payload),
                terms_accepted=True,
                privacy_accepted=True,
                public_display_authorized=True,
                fees_acknowledged=True,
                submitted_at=now,
                reviewed_by=submitter.id,
                reviewed_at=now,
                review_reason="Seeded from legacy hosted development API for QA coverage.",
            )
            db.add(submission)

        for submission, item, payload in planned_updates:
            submission.status = "active"
            submission.current_step = 7
            submission.last_completed_step = 7
            submission.payload = payload
            submission.step_completion = compute_step_completion(payload)
            submission.terms_accepted = True
            submission.privacy_accepted = True
            submission.public_display_authorized = True
            submission.fees_acknowledged = True
            submission.submitted_at = submission.submitted_at or now
            submission.reviewed_by = submitter.id
            submission.reviewed_at = now
            submission.review_reason = "Seeded from legacy hosted development API for QA coverage."

        db.commit()
        print(
            {
                "inserted": len(planned_inserts),
                "updated": len(planned_updates),
                "submitter": submitter.email,
            }
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
