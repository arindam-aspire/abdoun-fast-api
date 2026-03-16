"""
Check the current status of data in all tables.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func, select
from app.db.session import SessionLocal
from app.models.property_normalized import (
    PropertyCategory,
    PropertyType,
    City,
    Area,
    PropertyStatus,
    Feature,
    SearchField,
    CategoryFeature,
    TypeFeature,
    CategorySearchField,
    PropertyNormalized,
    PropertyFeature,
    PropertyTranslation,
)


def check_table_counts(db):
    """Check row counts for all tables."""
    tables = {
        "property_categories": PropertyCategory,
        "property_types": PropertyType,
        "cities": City,
        "areas": Area,
        "property_status": PropertyStatus,
        "features": Feature,
        "search_fields": SearchField,
        "category_features": CategoryFeature,
        "type_features": TypeFeature,
        "category_search_fields": CategorySearchField,
        "properties_normalized": PropertyNormalized,
        "property_features": PropertyFeature,
        "property_translations": PropertyTranslation,
    }
    
    print("=" * 60)
    print("Database Table Status")
    print("=" * 60)
    print()
    
    for table_name, model in tables.items():
        count = db.execute(select(func.count()).select_from(model)).scalar() or 0
        status = "YES" if count > 0 else "NO"
        print(f"{status} {table_name:30} : {count:5} rows")

    # property_translations by language (en, ar, esp, fr)
    trans_total = db.execute(select(func.count(PropertyTranslation.id))).scalar() or 0
    if trans_total > 0:
        print()
        print("  property_translations by language:")
        for lang in ("en", "ar", "esp", "fr"):
            c = db.execute(
                select(func.count(PropertyTranslation.id)).where(
                    PropertyTranslation.language_code == lang
                )
            ).scalar() or 0
            print(f"    {lang}: {c}")
    
    print()
    print("=" * 60)


def main():
    db = SessionLocal()
    try:
        check_table_counts(db)
        
        # Additional checks
        prop_count = db.execute(select(func.count(PropertyNormalized.id))).scalar() or 0
        if prop_count > 0:
            print("Properties exist in database")
            print(f"  Total properties: {prop_count}")
            
            # Check a sample property
            sample = db.execute(
                select(PropertyNormalized).limit(1)
            ).scalar_one_or_none()
            
            if sample:
                print(f"\n  Sample property:")
                print(f"    ID: {sample.id}")
                print(f"    Title: {sample.title}")
                print(f"    URL: {sample.url}")
        else:
            print("No properties found in database")
            print("  Run: python scripts/import_normalized_csv.py")
        
    finally:
        db.close()


if __name__ == "__main__":
    main()

