"""
Script to mark properties as exclusive based on approved logic.

Logic: A property is exclusive if ALL 3 conditions are met:
1. High Price: Selling > 800,000 JOD OR Rent > 45,000 JOD
2. Premium Location: Abdoun, Dabouq, Dair Gbhar, Al Rabieh, Al Sweifieh
3. Premium Type: Detached or Semi-Detached
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, or_, and_, func, text
from sqlalchemy.orm import Session
from app.db.session import SessionLocal

# Approved criteria
SELLING_PRICE_THRESHOLD = 800000
RENT_PRICE_THRESHOLD = 45000
PREMIUM_AREAS = ['abdoun', 'dabouq', 'dair gbhar', 'al rabieh', 'sweifieh', 'al sweifieh']
# Note: In database, "Detached" and "Semi-Detached" from CSV are mapped to "Villa" in property_types
PREMIUM_TYPES = ['villa', 'detached', 'semi-detached', 'semi']


def is_exclusive_property(property_obj) -> bool:
    """
    Check if property meets ALL exclusive criteria.
    
    Returns True if:
    1. High price (selling > 800K OR rent > 45K)
    2. Premium location (Abdoun, Dabouq, etc.)
    3. Premium type (Detached/Semi-Detached)
    """
    # Price check
    high_price = (
        (property_obj.selling_price_amount and property_obj.selling_price_amount > SELLING_PRICE_THRESHOLD) or
        (property_obj.rent_price_amount and property_obj.rent_price_amount > RENT_PRICE_THRESHOLD)
    )
    
    if not high_price:
        return False
    
    # Location check
    area_name = (property_obj.area_rel.name if property_obj.area_rel else '').lower()
    premium_location = any(premium in area_name for premium in PREMIUM_AREAS)
    
    if not premium_location:
        return False
    
    # Type check
    type_name = (property_obj.type.name if property_obj.type else '').lower()
    premium_type = any(premium in type_name for premium in PREMIUM_TYPES)
    
    return premium_type


def update_exclusive_properties(db: Session, dry_run: bool = False):
    """
    Update is_exclusive field for all properties based on approved logic.
    
    Args:
        db: Database session
        dry_run: If True, only show what would be updated without making changes
    """
    print("=" * 70)
    print("UPDATING EXCLUSIVE PROPERTIES")
    print("=" * 70)
    print(f"\nCriteria:")
    print(f"  1. High Price: Selling > {SELLING_PRICE_THRESHOLD:,} JOD OR Rent > {RENT_PRICE_THRESHOLD:,} JOD")
    print(f"  2. Premium Location: {', '.join(PREMIUM_AREAS)}")
    print(f"  3. Premium Type: {', '.join(PREMIUM_TYPES)}")
    print(f"\nLogic: ALL 3 conditions must be met")
    
    if dry_run:
        print("\n[DRY RUN MODE] - No changes will be made to database")
    
    # Load all properties with area and type info using raw SQL
    query = text("""
        SELECT 
            p.id,
            p.selling_price_amount,
            p.rent_price_amount,
            p.is_exclusive,
            a.name as area_name,
            pt.name as type_name
        FROM properties_normalized p
        LEFT JOIN areas a ON p.location_id = a.id
        LEFT JOIN property_types pt ON p.type_id = pt.id
    """)
    
    results = db.execute(query).fetchall()
    
    total = len(results)
    exclusive_count = 0
    updated_count = 0
    unchanged_count = 0
    updates_to_make = []
    
    print(f"\nProcessing {total:,} properties...")
    
    for row in results:
        prop_id = row[0]
        selling_price = float(row[1]) if row[1] else None
        rent_price = float(row[2]) if row[2] else None
        is_currently_exclusive = bool(row[3]) if row[3] is not None else False
        area_name = (row[4] or '').lower()
        type_name = (row[5] or '').lower()
        
        # Check criteria
        high_price = (
            (selling_price and selling_price > SELLING_PRICE_THRESHOLD) or
            (rent_price and rent_price > RENT_PRICE_THRESHOLD)
        )
        
        premium_location = any(premium in area_name for premium in PREMIUM_AREAS)
        premium_type = any(premium in type_name for premium in PREMIUM_TYPES)
        
        should_be_exclusive = high_price and premium_location and premium_type
        
        if should_be_exclusive:
            exclusive_count += 1
            
            if not is_currently_exclusive:
                updates_to_make.append((prop_id, True))
                updated_count += 1
            else:
                unchanged_count += 1
        else:
            if is_currently_exclusive:
                updates_to_make.append((prop_id, False))
                updated_count += 1
    
    if not dry_run and updates_to_make:
        # Batch update using raw SQL
        for prop_id, is_exclusive in updates_to_make:
            db.execute(
                text("UPDATE properties_normalized SET is_exclusive = :is_exclusive WHERE id = :id"),
                {"id": prop_id, "is_exclusive": is_exclusive}
            )
        db.commit()
        print(f"\n[OK] Database updated successfully!")
    elif updates_to_make:
        print(f"\n[DRY RUN] Would update {updated_count} properties")
    
    print("\n" + "=" * 70)
    print("RESULTS:")
    print("=" * 70)
    print(f"Total Properties: {total:,}")
    print(f"Exclusive Properties: {exclusive_count:,} ({exclusive_count/total*100:.1f}%)")
    print(f"Updated: {updated_count:,}")
    print(f"Unchanged: {unchanged_count:,}")
    print("=" * 70)
    
    return exclusive_count, updated_count


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Update exclusive properties based on approved logic")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes"
    )
    
    args = parser.parse_args()
    
    db = SessionLocal()
    try:
        update_exclusive_properties(db, dry_run=args.dry_run)
    except Exception as e:
        db.rollback()
        print(f"\n[ERROR] Error updating exclusive properties: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

