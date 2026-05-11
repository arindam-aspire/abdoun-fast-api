"""Reassign properties from one city/area to another, then cleanup old rows.

Use this to handle the full flow in one script:
1) move properties off the old location
2) delete old area (if no references remain)
3) delete old city (if no references remain)

Dry-run is default. Use ``--execute`` to apply changes.

Example:
  python scripts/reassign_and_cleanup_location.py \
    --from-city-id 6 --from-area-id 18 \
    --to-city-id 1 --to-area-id 11

  python scripts/reassign_and_cleanup_location.py \
    --from-city-id 6 --from-area-id 18 \
    --to-city-id 1 --to-area-id 11 \
    --execute
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import delete, func, select

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import SessionLocal
from app.models.property_normalized import Area, City, PropertyNormalized
from app.models.user import User  # noqa: F401 - register User for mapper resolution


def _count_properties_on_pair(db, city_id: int, area_id: int) -> int:
    return (
        db.execute(
            select(func.count())
            .select_from(PropertyNormalized)
            .where(
                PropertyNormalized.city_id == city_id,
                PropertyNormalized.location_id == area_id,
            )
        ).scalar()
        or 0
    )


def _count_properties_for_city(db, city_id: int) -> int:
    return (
        db.execute(
            select(func.count())
            .select_from(PropertyNormalized)
            .where(PropertyNormalized.city_id == city_id)
        ).scalar()
        or 0
    )


def _count_properties_for_area(db, area_id: int) -> int:
    return (
        db.execute(
            select(func.count())
            .select_from(PropertyNormalized)
            .where(PropertyNormalized.location_id == area_id)
        ).scalar()
        or 0
    )


def _count_areas_for_city(db, city_id: int) -> int:
    return (
        db.execute(select(func.count()).select_from(Area).where(Area.city_id == city_id)).scalar() or 0
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reassign properties to a target city/area and delete old city/area when safe."
    )
    parser.add_argument("--from-city-id", type=int, required=True, help="Source city id to cleanup.")
    parser.add_argument("--from-area-id", type=int, required=True, help="Source area id to cleanup.")
    parser.add_argument("--to-city-id", type=int, required=True, help="Target city id for reassignment.")
    parser.add_argument("--to-area-id", type=int, required=True, help="Target area id for reassignment.")
    parser.add_argument(
        "--only-if-from-city-name",
        type=str,
        default=None,
        help="Abort unless source city name matches exactly.",
    )
    parser.add_argument(
        "--only-if-from-area-name",
        type=str,
        default=None,
        help="Abort unless source area name matches exactly.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply updates/deletes. Without this, only dry-run output is printed.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        from_city = db.execute(select(City).where(City.id == args.from_city_id)).scalar_one_or_none()
        from_area = db.execute(select(Area).where(Area.id == args.from_area_id)).scalar_one_or_none()
        to_city = db.execute(select(City).where(City.id == args.to_city_id)).scalar_one_or_none()
        to_area = db.execute(select(Area).where(Area.id == args.to_area_id)).scalar_one_or_none()

        if from_city is None:
            print(f"Abort: source city id={args.from_city_id} not found.")
            return 1
        if from_area is None:
            print(f"Abort: source area id={args.from_area_id} not found.")
            return 1
        if to_city is None:
            print(f"Abort: target city id={args.to_city_id} not found.")
            return 1
        if to_area is None:
            print(f"Abort: target area id={args.to_area_id} not found.")
            return 1

        if from_area.city_id != from_city.id:
            print(
                f"Abort: source area id={from_area.id} belongs to city_id={from_area.city_id}, "
                f"not source city_id={from_city.id}."
            )
            return 1
        if to_area.city_id != to_city.id:
            print(
                f"Abort: target area id={to_area.id} belongs to city_id={to_area.city_id}, "
                f"not target city_id={to_city.id}."
            )
            return 1

        if args.only_if_from_city_name is not None and from_city.name != args.only_if_from_city_name:
            print(
                f"Abort: source city name is {from_city.name!r}, expected "
                f"{args.only_if_from_city_name!r} (--only-if-from-city-name)."
            )
            return 1

        if args.only_if_from_area_name is not None and from_area.name != args.only_if_from_area_name:
            print(
                f"Abort: source area name is {from_area.name!r}, expected "
                f"{args.only_if_from_area_name!r} (--only-if-from-area-name)."
            )
            return 1

        if from_city.id == to_city.id and from_area.id == to_area.id:
            print("Abort: source and target city/area are identical; nothing to do.")
            return 1

        source_pair_props = _count_properties_on_pair(db, from_city.id, from_area.id)
        source_city_props = _count_properties_for_city(db, from_city.id)
        source_area_props = _count_properties_for_area(db, from_area.id)
        source_city_areas = _count_areas_for_city(db, from_city.id)

        print("Source:")
        print(f"  city id={from_city.id} name={from_city.name!r}")
        print(f"  area id={from_area.id} name={from_area.name!r} city_id={from_area.city_id}")
        print("Target:")
        print(f"  city id={to_city.id} name={to_city.name!r}")
        print(f"  area id={to_area.id} name={to_area.name!r} city_id={to_area.city_id}")
        print()
        print(f"Properties on exact source pair (city_id={from_city.id}, location_id={from_area.id}): {source_pair_props}")
        print(f"Properties still on source city_id={from_city.id}: {source_city_props}")
        print(f"Properties still on source area_id={from_area.id}: {source_area_props}")
        print(f"Areas still under source city_id={from_city.id}: {source_city_areas}")

        if not args.execute:
            print("\nDry-run only. Pass --execute to apply reassignment and cleanup.")
            return 0

        # Reassign only rows that are on both the source city + source area pair.
        updated = db.execute(
            PropertyNormalized.__table__.update()
            .where(
                PropertyNormalized.city_id == from_city.id,
                PropertyNormalized.location_id == from_area.id,
            )
            .values(city_id=to_city.id, location_id=to_area.id)
        ).rowcount or 0

        print(f"\nReassigned properties: {updated}")

        remaining_on_source_area = _count_properties_for_area(db, from_area.id)
        if remaining_on_source_area > 0:
            print(
                f"Cannot delete source area id={from_area.id}: "
                f"{remaining_on_source_area} properties still reference it."
            )
            db.rollback()
            return 1

        db.execute(delete(Area).where(Area.id == from_area.id))
        print(f"Deleted source area id={from_area.id}.")

        remaining_source_city_props = _count_properties_for_city(db, from_city.id)
        remaining_source_city_areas = _count_areas_for_city(db, from_city.id)

        if remaining_source_city_props > 0 or remaining_source_city_areas > 0:
            print(
                f"Cannot delete source city id={from_city.id}: "
                f"remaining properties={remaining_source_city_props}, "
                f"remaining areas={remaining_source_city_areas}."
            )
            db.rollback()
            return 1

        db.execute(delete(City).where(City.id == from_city.id))
        print(f"Deleted source city id={from_city.id}.")

        db.commit()
        print("Done.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
