"""
Optional: backfill PropertyFeature.value from CSV more_features.

The API builds the structured features object (finishing, windows, etc.) from
properties_normalized.more_features JSON only. This script is not required for
the API response; use it only if you need value slots in the property_features
table (e.g. for search/filtering).

- Parses key|value pairs from CSV more_features.
- For each key that exists as Feature.name in DB, ensures a PropertyFeature row
  and sets PropertyFeature.value.

Does NOT touch properties_normalized.more_features (that is set on import).

Usage:
  python scripts/backfill_feature_values_from_csv.py
  python scripts/backfill_feature_values_from_csv.py --csv-path data/abdoun_merged_properties.csv
  python scripts/backfill_feature_values_from_csv.py --dry-run
"""
import sys
from pathlib import Path
from typing import Dict

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.property_normalized import (
    PropertyNormalized as Property,
    Feature,
    PropertyFeature,
)


def _normalize_str(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    return s if s and s.lower() not in ("nan", "none", "") else None


def parse_more_features_row(more_features_raw: object) -> Dict[str, str]:
    """
    Parse a single CSV more_features string into key->value dict.

    - Treat even indices as keys, odd indices as values.
    - Keep ALL keys that have a non-empty value; we will later
      intersect them with the Feature table in DB.

    Example input:
        "Finishing|Deluxe|Windows|Double Glazed|Window Shutters|Electric|Air Conditioning|Central|Heating System|Central"
    Output:
        {
          "Finishing": "Deluxe",
          "Windows": "Double Glazed",
          "Window Shutters": "Electric",
          "Air Conditioning": "Central",
          "Heating System": "Central"
        }
    """
    s = _normalize_str(more_features_raw)
    if not s:
        return {}
    parts = [p.strip() for p in s.split("|") if p.strip()]
    if not parts:
        return {}

    out: Dict[str, str] = {}
    # Treat even indices as keys, odd indices as values
    for i in range(0, len(parts) - 1, 2):
        key = parts[i]
        val = parts[i + 1] if i + 1 < len(parts) else None
        if val:
            out[key] = val
    return out


def backfill_feature_values(csv_path: Path, dry_run: bool = False) -> tuple[int, int]:
    """
    Backfill PropertyFeature.value from CSV more_features.

    Returns:
        (updated_rows, skipped_properties_without_match)
    """
    db = SessionLocal()
    try:
        df = pd.read_csv(csv_path)
        if "url" not in df.columns or "more_features" not in df.columns:
            print("CSV must have 'url' and 'more_features' columns.")
            return 0, 0

        # Build url -> {key: value} map from CSV
        url_to_feature_values: Dict[str, Dict[str, str]] = {}
        for _, row in df.iterrows():
            url_raw = row.get("url")
            url = _normalize_str(url_raw)
            if not url:
                continue
            kv = parse_more_features_row(row.get("more_features"))
            if kv:
                url_to_feature_values[url] = kv

        if not url_to_feature_values:
            print("No feature key/value pairs found in CSV more_features.")
            return 0, 0

        # Preload ALL Feature rows; we will only use keys that exist in this table
        feature_by_name: Dict[str, Feature] = {}
        existing_features = db.execute(select(Feature)).scalars().all()
        for feat in existing_features:
            feature_by_name[feat.name] = feat

        # Load properties by URL
        urls = list(url_to_feature_values.keys())
        props = (
            db.execute(select(Property).where(Property.url.in_(urls)))
            .scalars()
            .all()
        )
        props_by_url: Dict[str, Property] = {p.url: p for p in props if p.url}

        updated = 0
        skipped_no_match = 0

        for url, kv in url_to_feature_values.items():
            prop = props_by_url.get(url)
            if not prop:
                skipped_no_match += 1
                continue

            for key, val in kv.items():
                feature = feature_by_name.get(key)
                if not feature:
                    # We warned above; skip silently here.
                    continue

                # Get or create PropertyFeature row
                pf = db.execute(
                    select(PropertyFeature).where(
                        PropertyFeature.property_id == prop.id,
                        PropertyFeature.feature_id == feature.id,
                    )
                ).scalar_one_or_none()

                if pf is None:
                    pf = PropertyFeature(
                        property_id=prop.id,
                        feature_id=feature.id,
                        value=val,
                    )
                    if dry_run:
                        print(
                            f"[dry-run] would create PropertyFeature(property_id={prop.id}, "
                            f"feature_id={feature.id}, value={val!r}) for url={url!r}"
                        )
                    else:
                        db.add(pf)
                    updated += 1
                else:
                    if pf.value == val:
                        continue
                    if dry_run:
                        print(
                            f"[dry-run] would update PropertyFeature(property_id={prop.id}, "
                            f"feature_id={feature.id}) value from {pf.value!r} to {val!r} "
                            f"for url={url!r}"
                        )
                    else:
                        pf.value = val
                    updated += 1

        if not dry_run and updated:
            db.commit()

        return updated, skipped_no_match
    finally:
        db.close()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Backfill PropertyFeature.value from CSV more_features. "
            "All key|value pairs in CSV that have a matching Feature.name in DB "
            "will be written to PropertyFeature.value."
        )
    )
    parser.add_argument(
        "--csv-path",
        type=Path,
        default=Path("data/abdoun_merged_properties.csv"),
        help="Path to CSV file (default: data/abdoun_merged_properties.csv)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print changes that would be made without committing to DB",
    )
    args = parser.parse_args()

    if not args.csv_path.exists():
        print(f"CSV not found: {args.csv_path}")
        sys.exit(1)

    print("Backfilling feature values from CSV more_features...")
    print(f"  CSV: {args.csv_path}")
    print(f"  Dry run: {args.dry_run}")

    updated, skipped = backfill_feature_values(args.csv_path, dry_run=args.dry_run)

    print(f"\nSummary:")
    print(f"  Updated / created PropertyFeature rows: {updated}")
    print(f"  CSV rows with no matching property URL in DB: {skipped}")


if __name__ == "__main__":
    main()


