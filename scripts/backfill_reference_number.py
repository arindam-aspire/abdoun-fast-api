"""
Backfill reference_number on properties_normalized from CSV property_id.

Matches existing rows by url and sets reference_number from the CSV property_id column.
Run after migration 0008_add_reference_number.

Usage:
  python scripts/backfill_reference_number.py
  python scripts/backfill_reference_number.py --csv-path data/abdoun_merged_properties.csv
  python scripts/backfill_reference_number.py --dry-run
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.property_normalized import PropertyNormalized


def _normalize_ref(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    return s if s and s.lower() not in ("nan", "none", "") else None


def backfill_reference_number(csv_path: Path, dry_run: bool = False) -> tuple[int, int]:
    """
    Update reference_number for properties_normalized from CSV (match by url).

    Returns:
        (updated_count, skipped_no_match)
    """
    db = SessionLocal()
    try:
        df = pd.read_csv(csv_path)
        if "url" not in df.columns or "property_id" not in df.columns:
            print("CSV must have 'url' and 'property_id' columns.")
            return 0, 0

        # Build url -> reference_number from CSV
        url_to_ref = {}
        for _, row in df.iterrows():
            url_raw = row.get("url")
            if url_raw is None or (isinstance(url_raw, float) and pd.isna(url_raw)):
                continue
            url = str(url_raw).strip()
            if not url:
                continue
            ref = _normalize_ref(row.get("property_id"))
            if ref is not None:
                url_to_ref[url] = ref

        if not url_to_ref:
            print("No url/property_id pairs found in CSV.")
            return 0, 0

        # Load all properties that have a URL we care about
        urls = list(url_to_ref.keys())
        result = db.execute(
            select(PropertyNormalized).where(PropertyNormalized.url.in_(urls))
        )
        props = result.scalars().all()
        matched_urls = {p.url for p in props}

        updated = 0
        for prop in props:
            ref = url_to_ref.get(prop.url)
            if ref is None:
                continue
            if prop.reference_number == ref:
                continue
            if dry_run:
                print(f"  [dry-run] would set reference_number={ref!r} for url={prop.url!r}")
                updated += 1
                continue
            prop.reference_number = ref
            updated += 1

        if not dry_run and updated:
            db.commit()
        skipped = len(url_to_ref) - len(matched_urls)  # CSV URLs with no matching row in DB
        return updated, skipped
    finally:
        db.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Backfill reference_number from CSV property_id")
    parser.add_argument(
        "--csv-path",
        type=Path,
        default=Path("data/abdoun_merged_properties.csv"),
        help="Path to CSV with url and property_id columns",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print what would be updated, do not commit")
    args = parser.parse_args()

    if not args.csv_path.exists():
        print(f"CSV not found: {args.csv_path}")
        sys.exit(1)

    print("Backfilling reference_number from CSV...")
    print(f"  CSV: {args.csv_path}")
    print(f"  Dry run: {args.dry_run}")
    updated, skipped = backfill_reference_number(args.csv_path, dry_run=args.dry_run)
    print(f"  Updated: {updated}")
    if skipped > 0:
        print(f"  Skipped (no matching URL in DB): {skipped}")
    print("Done.")


if __name__ == "__main__":
    main()
