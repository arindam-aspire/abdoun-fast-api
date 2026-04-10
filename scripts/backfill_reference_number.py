"""
Backfill reference_number on properties_normalized from CSV property_id.

Matches existing rows by url and sets reference_number from the CSV property_id column.
Run after migration 0008_add_reference_number.

Usage:
  python scripts/backfill_reference_number.py
  python scripts/backfill_reference_number.py --csv-path data/abdoun_merged_properties.csv
  python scripts/backfill_reference_number.py --dry-run
  python scripts/backfill_reference_number.py --verify   # read-only: compare CSV vs DB
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from sqlalchemy import select, update

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

        # Load only columns we need — avoids huge rows (geometry, JSON, text) and
        # relationship selectin loads on full PropertyNormalized instances.
        urls = list(url_to_ref.keys())
        rows = db.execute(
            select(
                PropertyNormalized.id,
                PropertyNormalized.url,
                PropertyNormalized.reference_number,
            ).where(PropertyNormalized.url.in_(urls))
        ).all()
        matched_urls = {r.url for r in rows}

        updated = 0
        for row in rows:
            url = row.url
            ref = url_to_ref.get(url)
            if ref is None:
                continue
            if row.reference_number == ref:
                continue
            if dry_run:
                print(f"  [dry-run] would set reference_number={ref!r} for url={url!r}")
                updated += 1
                continue
            db.execute(
                update(PropertyNormalized)
                .where(PropertyNormalized.id == row.id)
                .values(reference_number=ref)
            )
            updated += 1

        if not dry_run and updated:
            db.commit()
        skipped = len(url_to_ref) - len(matched_urls)  # CSV URLs with no matching row in DB
        return updated, skipped
    finally:
        db.close()


def verify_reference_numbers(csv_path: Path, sample_mismatches: int = 15) -> int:
    """
    Read-only: compare CSV property_id (per url) to DB reference_number.

    Returns:
        Exit-style code: 0 if all matched rows agree with CSV, else 1.
    """
    db = SessionLocal()
    try:
        df = pd.read_csv(csv_path)
        if "url" not in df.columns or "property_id" not in df.columns:
            print("CSV must have 'url' and 'property_id' columns.")
            return 1

        url_to_ref: dict[str, str] = {}
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
            return 1

        urls = list(url_to_ref.keys())
        rows = db.execute(
            select(
                PropertyNormalized.url,
                PropertyNormalized.reference_number,
            ).where(PropertyNormalized.url.in_(urls))
        ).all()

        by_url = {r.url: r.reference_number for r in rows}
        matched = len(by_url)
        expected_csv_rows = len(url_to_ref)
        not_in_db = expected_csv_rows - matched

        mismatches: list[tuple[str, str, str | None]] = []
        for url, expected in url_to_ref.items():
            if url not in by_url:
                continue
            actual = by_url[url]
            # Same rule as backfill: exact equality after CSV normalization
            if actual != expected:
                mismatches.append((url, expected, actual))

        print("Verify reference_number (read-only, no DB writes)")
        print(f"  CSV: {csv_path}")
        print(f"  CSV rows with url + property_id: {expected_csv_rows}")
        print(f"  Matched URLs in DB: {matched}")
        print(f"  CSV URLs not found in DB: {not_in_db}")
        print(f"  Rows where DB reference_number != CSV property_id: {len(mismatches)}")

        if mismatches:
            print("\n  Sample mismatches (url, CSV property_id, DB reference_number):")
            for url, exp, act in mismatches[:sample_mismatches]:
                print(f"    {url!r}")
                print(f"      CSV expects: {exp!r}  DB has: {act!r}")
            if len(mismatches) > sample_mismatches:
                print(f"    ... and {len(mismatches) - sample_mismatches} more")

        ok = len(mismatches) == 0
        if ok and not_in_db == 0:
            print("\n  OK: Every CSV reference matches the database, and every CSV URL exists in the DB.")
        elif ok:
            print(
                "\n  OK: Every *matched* URL has the correct reference_number. "
                "Some CSV URLs are missing in the DB (see count above); fix import or CSV if that is unexpected."
            )
        else:
            print("\n  FAIL: Run without --verify (or use --dry-run) to see what the backfill would change.")

        return 0 if ok else 1
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
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Read-only: compare CSV property_id to DB reference_number; exit 1 if any mismatch",
    )
    args = parser.parse_args()

    if not args.csv_path.exists():
        print(f"CSV not found: {args.csv_path}")
        sys.exit(1)

    if args.verify:
        sys.exit(verify_reference_numbers(args.csv_path))

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
