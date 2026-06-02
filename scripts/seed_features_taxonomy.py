"""
Seed feature / amenity taxonomy rows on the extended ``features`` table.

Run after ``scripts/seed_reference_data.py`` (categories and property types must exist).

Usage:
    python scripts/seed_features_taxonomy.py
    python scripts/seed_features_taxonomy.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.property_normalized import Feature, PropertyCategory, PropertyType
from app.utils.constants import FeatureGroup

RESIDENTIAL_AMENITIES = [
    "Parking",
    "Elevator",
    "Swimming Pool",
    "Security",
    "Garden",
    "Balcony",
    "Central Air Conditioning",
]

COMMERCIAL_AMENITIES = [
    "Parking",
    "Elevator",
    "Security",
    "Reception",
    "Loading Dock",
]

LAND_AMENITIES = [
    "Water Well",
    "Electricity",
    "Road Access",
    "Fenced",
]

APARTMENT_FEATURES = [
    "Penthouse",
    "Duplex",
    "Studio Layout",
    "Maid's Room",
]

VILLA_FEATURES = [
    "Maid's Room",
    "Driver's Room",
    "Private Pool",
    "Detached Guest House",
]

OFFICE_FEATURES = [
    "Meeting Room",
    "Open Plan",
    "Reception Area",
    "Server Room",
]

LAND_TYPE_FEATURES = [
    "Corner Plot",
    "Sloped",
    "Agricultural Zoning",
]


def _slugify(name: str, *, category_slug: str, feature_group: str, type_slug: str | None) -> str:
    base = (
        name.lower()
        .replace("'", "")
        .replace(" ", "-")
        .replace("/", "-")
    )
    parts = [base, category_slug, feature_group.lower()]
    if type_slug:
        parts.append(type_slug)
    return "-".join(parts)


def _get_category(db: Session, slug: str) -> PropertyCategory | None:
    return db.query(PropertyCategory).filter(PropertyCategory.slug == slug).first()


def _get_type(db: Session, slug: str, category_id: int) -> PropertyType | None:
    return (
        db.query(PropertyType)
        .filter(PropertyType.slug == slug, PropertyType.category_id == category_id)
        .first()
    )


def _upsert_feature(
    db: Session,
    *,
    name: str,
    category: PropertyCategory,
    property_type: PropertyType | None,
    feature_group: str,
    display_order: int,
    dry_run: bool,
) -> None:
    type_slug = property_type.slug if property_type else None
    slug = _slugify(
        name,
        category_slug=category.slug,
        feature_group=feature_group,
        type_slug=type_slug,
    )
    property_type_id = property_type.id if property_type else None

    existing = db.query(Feature).filter(Feature.slug == slug).first()
    if existing:
        print(f"  skip (exists): {name} [{feature_group}]")
        return

    if dry_run:
        print(f"  would create: {name} [{feature_group}] slug={slug}")
        return

    row = Feature(
        name=name,
        slug=slug,
        category_id=category.id,
        property_type_id=property_type_id,
        feature_group=feature_group,
        display_order=display_order,
        is_active=True,
    )
    db.add(row)
    print(f"  created: {name} [{feature_group}]")


def seed_amenities(db: Session, *, dry_run: bool) -> None:
    mapping = [
        ("residential", RESIDENTIAL_AMENITIES),
        ("commercial", COMMERCIAL_AMENITIES),
        ("land", LAND_AMENITIES),
    ]
    for category_slug, names in mapping:
        category = _get_category(db, category_slug)
        if not category:
            print(f"Category missing: {category_slug}")
            continue
        print(f"Amenities for {category.name}:")
        for order, name in enumerate(names, start=1):
            _upsert_feature(
                db,
                name=name,
                category=category,
                property_type=None,
                feature_group=FeatureGroup.AMENITY,
                display_order=order,
                dry_run=dry_run,
            )


def seed_type_features(db: Session, *, dry_run: bool) -> None:
    specs = [
        ("residential", "apartment", APARTMENT_FEATURES),
        ("residential", "villa", VILLA_FEATURES),
        ("commercial", "office", OFFICE_FEATURES),
        ("land", "land", LAND_TYPE_FEATURES),
    ]
    for category_slug, type_slug, names in specs:
        category = _get_category(db, category_slug)
        if not category:
            print(f"Category missing: {category_slug}")
            continue
        prop_type = _get_type(db, type_slug, category.id)
        if not prop_type:
            print(f"Type missing: {type_slug} ({category_slug})")
            continue
        print(f"Features for {category.name} / {prop_type.name}:")
        for order, name in enumerate(names, start=1):
            _upsert_feature(
                db,
                name=name,
                category=category,
                property_type=prop_type,
                feature_group=FeatureGroup.FEATURE,
                display_order=order,
                dry_run=dry_run,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed extended features taxonomy")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        print("Seeding category amenities...")
        seed_amenities(db, dry_run=args.dry_run)
        print("Seeding property-type features...")
        seed_type_features(db, dry_run=args.dry_run)
        if not args.dry_run:
            db.commit()
            print("Done.")
        else:
            db.rollback()
            print("Dry run complete (no changes committed).")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
