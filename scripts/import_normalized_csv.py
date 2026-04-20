"""
Import CSV data into normalized property structure.

Usage:
    python scripts/import_normalized_csv.py [--csv-path path/to/file.csv] [--geocode-missing]
"""
import sys
import argparse
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from app.db.session import SessionLocal
import app.models  # noqa: F401  # Ensure all ORM mappers are registered before queries
import app.models.user  # noqa: F401  # Ensure User mapper is registered for favorites relationship resolution
from app.services.normalized_importer import import_properties_normalized_from_dataframe


def main():
    parser = argparse.ArgumentParser(description="Import CSV data into normalized property structure")
    parser.add_argument(
        "--csv-path",
        type=str,
        default="data/abdoun_merged_properties.csv",
        help="Path to CSV file (default: data/abdoun_merged_properties.csv)"
    )
    parser.add_argument(
        "--geocode-missing",
        action="store_true",
        help="Geocode locations that don't have coordinates (slower, rate-limited)"
    )
    parser.add_argument(
        "--skip-duplicates",
        action="store_true",
        default=True,
        help="Skip properties that already exist (by URL)"
    )
    
    args = parser.parse_args()
    
    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        print(f"Error: CSV file not found at {csv_path}")
        sys.exit(1)
    
    print("=" * 60)
    print("Importing Properties to Normalized Structure")
    print("=" * 60)
    print(f"CSV File: {csv_path}")
    print(f"Geocode Missing: {args.geocode_missing}")
    print(f"Skip Duplicates: {args.skip_duplicates}")
    print()
    
    # Read CSV
    print("Reading CSV file...")
    try:
        df = pd.read_csv(csv_path)
        print(f"Loaded {len(df)} rows from CSV")
    except Exception as e:
        print(f"Error reading CSV: {e}")
        sys.exit(1)
    
    # Import to database
    db = SessionLocal()
    try:
        print()
        print("Importing properties...")
        imported_count = import_properties_normalized_from_dataframe(
            db=db,
            df=df,
            geocode_missing=args.geocode_missing,
            skip_duplicates=args.skip_duplicates,
        )
        
        print()
        print("=" * 60)
        print(f"Import completed successfully!")
        print(f"  Imported: {imported_count} properties")
        print("=" * 60)
        
    except Exception as e:
        db.rollback()
        print(f"Error importing data: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()

