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
  python scripts/backfill_meta_features_from_csv.py --verify   # read-only: CSV vs property_features
"""
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.models.property_normalized import Feature, PropertyFeature, PropertyNormalized as Property
from app.services.normalized_importer import (
    META_FEATURE_COLUMNS,
    _meta_feature_value,
    _slugify,
    add_property_meta_features,
)

# Smaller batches = shorter transactions (helps flaky remote SSL / proxy timeouts).
_BATCH_COMMIT = 100
_URL_LOOKUP_CHUNK = 400
_MAX_RETRIES = 5


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

        props_by_url: dict[str, UUID] = {}
        for i in range(0, len(urls), _URL_LOOKUP_CHUNK):
            chunk = urls[i : i + _URL_LOOKUP_CHUNK]
            rows = db.execute(
                select(Property.id, Property.url).where(Property.url.in_(chunk))
            ).all()
            for r in rows:
                if r.url:
                    props_by_url[r.url] = r.id

        updated = 0
        skipped = 0
        work: list[tuple[UUID, pd.Series]] = []
        for _, row in df.iterrows():
            url = _normalize_str(row.get("url"))
            if not url:
                continue
            prop_id = props_by_url.get(url)
            if not prop_id:
                skipped += 1
                continue
            updated += 1
            if dry_run:
                print(f"[dry-run] would add meta features for url={url!r}")
            else:
                work.append((prop_id, row))

        if dry_run:
            return updated, skipped

        feature_cache: dict[str, Feature] = {}
        for start in range(0, len(work), _BATCH_COMMIT):
            batch = work[start : start + _BATCH_COMMIT]
            last_exc: OperationalError | None = None
            for attempt in range(_MAX_RETRIES):
                try:
                    for prop_id, row in batch:
                        add_property_meta_features(db, prop_id, row, feature_cache)
                    db.commit()
                    last_exc = None
                    break
                except OperationalError as exc:
                    last_exc = exc
                    try:
                        db.rollback()
                    except Exception:
                        pass
                    db.close()
                    db = SessionLocal()
                    feature_cache.clear()
                    print(
                        f"  Warning: database error ({exc.__class__.__name__}), "
                        f"reconnecting — retry batch {start // _BATCH_COMMIT + 1} "
                        f"(attempt {attempt + 1}/{_MAX_RETRIES})"
                    )
            if last_exc is not None:
                raise last_exc

        return updated, skipped
    finally:
        db.close()


def verify_meta_features_from_csv(csv_path: Path, sample_mismatches: int = 15) -> int:
    """
    Read-only: for each CSV row with a URL present in the DB, compare
    _meta_feature_value(...) to property_features.value (joined via features.slug).

    Only checks columns where the CSV yields a non-empty value (same as backfill writes).
    Duplicate URLs in the CSV: last row wins (same as sequential backfill).

    Returns:
        0 if every expected pair matches DB, else 1.
    """
    db = SessionLocal()
    try:
        df = pd.read_csv(csv_path)
        if "url" not in df.columns:
            print("CSV must have 'url' column.")
            return 1

        urls = list(df["url"].dropna().unique())
        urls = [_normalize_str(u) for u in urls if _normalize_str(u)]
        if not urls:
            print("No valid URLs in CSV.")
            return 1

        props_by_url: dict[str, UUID] = {}
        for i in range(0, len(urls), _URL_LOOKUP_CHUNK):
            chunk = urls[i : i + _URL_LOOKUP_CHUNK]
            rows = db.execute(
                select(Property.id, Property.url).where(Property.url.in_(chunk))
            ).all()
            for r in rows:
                if r.url:
                    props_by_url[r.url] = r.id

        # Last row per URL among rows that match DB (mirrors backfill overwrite behavior).
        last_row_by_url: dict[str, pd.Series] = {}
        for _, row in df.iterrows():
            url = _normalize_str(row.get("url"))
            if not url or url not in props_by_url:
                continue
            last_row_by_url[url] = row

        meta_slugs = [_slugify(feature_name) for _, feature_name in META_FEATURE_COLUMNS]
        slug_to_fid: dict[str, int] = {}
        for r in db.execute(
            select(Feature.id, Feature.slug).where(Feature.slug.in_(meta_slugs))
        ).all():
            slug_to_fid[r.slug] = r.id

        expected_checks: list[tuple[str, UUID, str, str, str]] = []
        # (url, property_id, feature_slug, csv_column, expected_value)
        for url, row in last_row_by_url.items():
            prop_id = props_by_url[url]
            for csv_col, feature_name in META_FEATURE_COLUMNS:
                slug = _slugify(feature_name)
                exp = _meta_feature_value(row, csv_col)
                if not exp:
                    continue
                expected_checks.append((url, prop_id, slug, csv_col, exp))

        prop_ids = {pid for _, pid, _, _, _ in expected_checks}
        actual: dict[tuple[UUID, int], str | None] = {}
        prop_id_list = list(prop_ids)
        for i in range(0, len(prop_id_list), _URL_LOOKUP_CHUNK):
            chunk_ids = prop_id_list[i : i + _URL_LOOKUP_CHUNK]
            if not chunk_ids:
                continue
            q = (
                select(PropertyFeature.property_id, PropertyFeature.feature_id, PropertyFeature.value)
                .join(Feature, Feature.id == PropertyFeature.feature_id)
                .where(
                    PropertyFeature.property_id.in_(chunk_ids),
                    Feature.slug.in_(meta_slugs),
                )
            )
            for r in db.execute(q).all():
                actual[(r.property_id, r.feature_id)] = r.value

        mismatches: list[tuple[str, str, str, str | None]] = []
        # (url, csv_column, expected, actual_or_reason)
        missing_feature_slugs = set(meta_slugs) - set(slug_to_fid.keys())
        for url, prop_id, slug, csv_col, exp in expected_checks:
            if slug in missing_feature_slugs:
                mismatches.append((url, csv_col, exp, "<no Feature row for slug>"))
                continue
            fid = slug_to_fid[slug]
            got = actual.get((prop_id, fid))
            if got != exp:
                mismatches.append((url, csv_col, exp, got))

        csv_urls_with_meta = len(last_row_by_url)
        skipped_rows = 0
        for _, r in df.iterrows():
            u = _normalize_str(r.get("url"))
            if not u:
                continue
            if u not in props_by_url:
                skipped_rows += 1

        print("Verify meta features (read-only, no DB writes)")
        print(f"  CSV: {csv_path}")
        print(f"  Unique URLs in CSV (non-empty): {len(urls)}")
        print(f"  URLs resolved to a property: {len(props_by_url)}")
        print(f"  Last-row-by-URL rows used for expectations: {csv_urls_with_meta}")
        print(f"  CSV rows with URL not found in DB: {skipped_rows}")
        print(f"  Non-empty meta cells to check (property × column): {len(expected_checks)}")
        if missing_feature_slugs:
            print(f"  WARNING: Feature rows missing for slugs: {sorted(missing_feature_slugs)}")
        print(f"  Mismatches (missing row or wrong value): {len(mismatches)}")

        if mismatches:
            print("\n  Sample mismatches (url, csv_column, CSV expected, DB value or note):")
            for url, col, exp, act in mismatches[:sample_mismatches]:
                print(f"    {url!r}")
                print(f"      {col}: expected {exp!r}  got {act!r}")
            if len(mismatches) > sample_mismatches:
                print(f"    ... and {len(mismatches) - sample_mismatches} more")

        ok = len(mismatches) == 0
        if ok:
            print("\n  OK: Every non-empty CSV meta value matches property_features.")
        else:
            print("\n  FAIL: Re-run backfill or inspect CSV / DB for the mismatches above.")

        return 0 if ok else 1
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
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Read-only: compare CSV meta columns to property_features; exit 1 on mismatch",
    )
    parser.add_argument(
        "--sample-mismatches",
        type=int,
        default=15,
        help="With --verify, max mismatch lines to print (default: 15)",
    )
    args = parser.parse_args()

    if not args.csv_path.exists():
        print(f"CSV not found: {args.csv_path}")
        sys.exit(1)

    if args.verify:
        sys.exit(verify_meta_features_from_csv(args.csv_path, sample_mismatches=args.sample_mismatches))

    print("Backfilling meta features from CSV...")
    print(f"  CSV: {args.csv_path}")
    print(f"  Dry run: {args.dry_run}")
    updated, skipped = backfill_meta_features(args.csv_path, dry_run=args.dry_run)
    print("\nSummary:")
    print(f"  Properties updated: {updated}")
    print(f"  CSV rows with no matching URL in DB: {skipped}")


if __name__ == "__main__":
    main()
