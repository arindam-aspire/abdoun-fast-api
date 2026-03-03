"""
Backfill meta fields (floor type, floor, building_status, garage, terrace_area,
garden_area, master_bedrooms, kitchens, furniture) from CSV into property_features
as Feature + PropertyFeature.value.

CSV columns: type, floor, building_status, garage, terrace_area, garden_area,
master_bedrooms, kitchens, furniture.
Feature names: Floor Type, Floor, Building Status, Garage, Terrace Area,
Garden Area, Master Bedrooms, Kitchens, Furniture.

Matches properties by URL. Run after import to populate existing rows, or run
before re-import so new imports already have meta features.

Usage:
  python scripts/backfill_meta_features_from_csv.py
  python scripts/backfill_meta_features_from_csv.py --csv-path data/abdoun_merged_properties.csv
  python scripts/backfill_meta_features_from_csv.py --dry-run
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.property_normalized import PropertyNormalized as Property
from app.services.normalized_importer import add_property_meta_features


def _normalize_str(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    return s if s and s.lower() not in ("nan", "none", "") else None


def backfill_meta_features(csv_path: Path, dry_run: bool = False) -> tuple[int, int]:
    """
    Backfill PropertyFeature rows for meta columns (Floor Type, Floor, etc.) from CSV.
    Returns (updated_property_count, skipped_no_match).
    """
    db = SessionLocal()
    try:
        df = pd.read_csv(csv_path)
        if "url" not in df.columns:
            print("CSV must have 'url' column.")
            return 0, 0

        urls = list(df["url"].dropna().unique())
        urls = [_normalize_str(u) for u in urls if _normalize_str(u)]
        if not urls:
            print("No valid URLs in CSV.")
            return 0, 0

        props = (
            db.execute(select(Property).where(Property.url.in_(urls)))
            .scalars().all()
        )
        props_by_url = {p.url: p for p in props if p.url}

        updated = 0
        skipped = 0
        for _, row in df.iterrows():
            url = _normalize_str(row.get("url"))
            if not url:
                continue
            prop = props_by_url.get(url)
            if not prop:
                skipped += 1
                continue
            if dry_run:
                print(f"[dry-run] would add meta features for url={url!r}")
            else:
                add_property_meta_features(db, prop.id, row)
            updated += 1

        if not dry_run and updated:
            db.commit()
        return updated, skipped
    finally:
        db.close()


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Backfill Floor Type, Floor, Building Status, Garage, Terrace Area, Garden Area, Master Bedrooms, Kitchens, Furniture from CSV into property_features."
    )
    parser.add_argument(
        "--csv-path",
        type=Path,
        default=Path("data/abdoun_merged_properties.csv"),
        help="Path to CSV",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not commit")
    args = parser.parse_args()

    if not args.csv_path.exists():
        print(f"CSV not found: {args.csv_path}")
        sys.exit(1)

    print("Backfilling meta features from CSV...")
    print(f"  CSV: {args.csv_path}")
    print(f"  Dry run: {args.dry_run}")
    updated, skipped = backfill_meta_features(args.csv_path, dry_run=args.dry_run)
    print(f"\nSummary:")
    print(f"  Properties updated: {updated}")
    print(f"  CSV rows with no matching URL in DB: {skipped}")


if __name__ == "__main__":
    main()

