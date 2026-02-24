"""
Script to update more_features column for existing properties in the database.

This script reads the CSV file and updates only the more_features JSON column
for properties that already exist in the database.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import pandas as pd
from sqlalchemy import select, text, Table, MetaData
from sqlalchemy.orm import Session
from app.db.session import SessionLocal

# Import functions directly to avoid model import issues
def _split_pipe(value):
    """Split pipe-separated string into list."""
    if not value or pd.isna(value):
        return []
    return [item.strip() for item in str(value).split("|") if item.strip()]


def parse_more_features_to_json(more_features_list: list[str] | None) -> dict | None:
    """
    Parse pipe-separated more_features list into key-value JSON object.
    
    Example:
        Input: ['Finishing', 'Deluxe', 'Windows', 'Double Glazed', 'Heating System', 'Central']
        Output: {'Finishing': 'Deluxe', 'Windows': 'Double Glazed', 'Heating System': 'Central'}
    
    Args:
        more_features_list: List of strings from pipe-separated CSV column
        
    Returns:
        Dictionary with key-value pairs, or None if input is empty/invalid
    """
    if not more_features_list:
        return None
    
    # Filter out empty strings
    features = [f.strip() for f in more_features_list if f and f.strip()]
    
    if not features:
        return None
    
    # If odd number of items, ignore the last one (no matching value)
    if len(features) % 2 != 0:
        features = features[:-1]
    
    # Convert to key-value pairs
    result = {}
    for i in range(0, len(features), 2):
        key = features[i]
        value = features[i + 1] if i + 1 < len(features) else None
        if key and value:
            result[key] = value
    
    return result if result else None


def update_more_features_from_csv(csv_path: str = "data/abdoun_merged_properties.csv"):
    """
    Update more_features column for existing properties from CSV file.
    
    Args:
        csv_path: Path to the CSV file
    """
    print("=" * 60)
    print("Updating More Features Column")
    print("=" * 60)
    print(f"CSV File: {csv_path}\n")
    
    # Read CSV file
    print("Reading CSV file...")
    try:
        df = pd.read_csv(csv_path)
        print(f"[OK] Loaded {len(df)} rows from CSV\n")
    except Exception as e:
        print(f"[ERROR] Error reading CSV file: {e}")
        return
    
    # Initialize database session
    db = SessionLocal()
    
    try:
        updated_count = 0
        not_found_count = 0
        error_count = 0
        
        print("Updating more_features column...")
        
        for idx, row in df.iterrows():
            try:
                # Get URL from CSV row
                url = str(row.get("url") or "").strip()
                if not url:
                    continue
                
                # Parse more_features from CSV
                more_features_raw = row.get("more_features")
                if pd.isna(more_features_raw) or not more_features_raw:
                    continue
                
                # Split pipe-separated values
                more_features_list = _split_pipe(more_features_raw)
                
                # Parse to JSON object
                more_features_json = parse_more_features_to_json(more_features_list)
                
                if not more_features_json:
                    continue
                
                # Find property by URL using raw SQL to avoid model import issues
                result = db.execute(
                    text("SELECT id FROM properties_normalized WHERE url = :url"),
                    {"url": url}
                ).fetchone()
                
                if not result:
                    not_found_count += 1
                    continue
                
                # Update more_features column using raw SQL
                db.execute(
                    text("UPDATE properties_normalized SET more_features = :more_features WHERE url = :url"),
                    {
                        "more_features": json.dumps(more_features_json),
                        "url": url
                    }
                )
                db.commit()
                
                updated_count += 1
                
                # Progress indicator
                if (idx + 1) % 100 == 0:
                    print(f"  Processed {idx + 1}/{len(df)} rows...")
                    
            except Exception as e:
                db.rollback()
                error_count += 1
                print(f"  [ERROR] Error processing row {idx + 1}: {e}")
                continue
        
        print("\n" + "=" * 60)
        print("[OK] Update completed!")
        print(f"  Updated: {updated_count} properties")
        print(f"  Not found: {not_found_count} properties")
        print(f"  Errors: {error_count} properties")
        print("=" * 60)
        
    except Exception as e:
        db.rollback()
        print(f"\n[ERROR] Error during update: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Update more_features column for existing properties")
    parser.add_argument(
        "csv_file",
        nargs="?",
        default="data/abdoun_merged_properties.csv",
        help="Path to CSV file (default: data/abdoun_merged_properties.csv)"
    )
    
    args = parser.parse_args()
    update_more_features_from_csv(args.csv_file)
