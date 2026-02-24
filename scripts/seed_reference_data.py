"""
Seed reference data for normalized property structure.

This script populates the reference tables with initial data:
- Property Categories (Residential, Commercial, Land)
- Property Types (Apartment, Villa, Office, etc.)
- Cities (Amman, etc.)
- Areas (Abdoun, Khalda, etc.)
- Property Statuses (verified, pending, etc.)
- Common Features (Elevator, Parking, etc.)
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
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
)


def seed_categories(db: Session):
    """Seed property categories."""
    categories = [
        {"name": "Residential", "slug": "residential"},
        {"name": "Commercial", "slug": "commercial"},
        {"name": "Land", "slug": "land"},
    ]
    
    for cat_data in categories:
        existing = db.query(PropertyCategory).filter(
            PropertyCategory.slug == cat_data["slug"]
        ).first()
        if not existing:
            category = PropertyCategory(**cat_data, is_active=True)
            db.add(category)
            print(f"✓ Created category: {cat_data['name']}")
        else:
            print(f"⊘ Category already exists: {cat_data['name']}")
    
    db.commit()


def seed_property_types(db: Session):
    """Seed property types."""
    # Get categories
    residential = db.query(PropertyCategory).filter(
        PropertyCategory.slug == "residential"
    ).first()
    commercial = db.query(PropertyCategory).filter(
        PropertyCategory.slug == "commercial"
    ).first()
    land = db.query(PropertyCategory).filter(
        PropertyCategory.slug == "land"
    ).first()
    
    types = [
        # Residential types
        {"name": "Apartment", "slug": "apartment", "category": residential},
        {"name": "Villa", "slug": "villa", "category": residential},
        {"name": "House", "slug": "house", "category": residential},
        {"name": "Building", "slug": "building", "category": residential},
        {"name": "Farm", "slug": "farm", "category": residential},
        {"name": "Semi Villa", "slug": "semi-villa", "category": residential},
        {"name": "Roof", "slug": "roof", "category": residential},
        # Commercial types
        {"name": "Office", "slug": "office", "category": commercial},
        {"name": "Showroom", "slug": "showroom", "category": commercial},
        {"name": "Warehouse", "slug": "warehouse", "category": commercial},
        {"name": "Business", "slug": "business", "category": commercial},
        # Land types
        {"name": "Land", "slug": "land", "category": land},
        {"name": "Residential Land", "slug": "residential-land", "category": land},
        {"name": "Commercial Land", "slug": "commercial-land", "category": land},
    ]
    
    for type_data in types:
        category = type_data.pop("category")
        if not category:
            continue
        
        existing = db.query(PropertyType).filter(
            PropertyType.slug == type_data["slug"],
            PropertyType.category_id == category.id
        ).first()
        if not existing:
            prop_type = PropertyType(**type_data, category_id=category.id, is_active=True)
            db.add(prop_type)
            print(f"✓ Created type: {type_data['name']} ({category.name})")
        else:
            print(f"⊘ Type already exists: {type_data['name']}")
    
    db.commit()


def seed_cities(db: Session):
    """Seed cities."""
    cities = [
        {"name": "Amman"},
        {"name": "Irbid"},
        {"name": "Zarqa"},
        {"name": "Aqaba"},
        {"name": "Madaba"},
    ]
    
    for city_data in cities:
        existing = db.query(City).filter(
            City.name.ilike(city_data["name"])
        ).first()
        if not existing:
            city = City(**city_data, is_active=True)
            db.add(city)
            print(f"✓ Created city: {city_data['name']}")
        else:
            print(f"⊘ City already exists: {city_data['name']}")
    
    db.commit()


def seed_areas(db: Session):
    """Seed areas for Amman."""
    amman = db.query(City).filter(City.name.ilike("Amman")).first()
    if not amman:
        print("⚠ Amman city not found. Creating it first...")
        amman = City(name="Amman", is_active=True)
        db.add(amman)
        db.commit()
        db.refresh(amman)
    
    areas = [
        "Abdoun",
        "Khalda",
        "Dabouq",
        "Al Sweifieh",
        "Al Rawnaq",
        "Al Kursi",
        "4th Circle",
        "Jabal Amman",
        "Shmeisani",
        "Jubeiha",
        "Tla' Al Ali",
        "Wadi Al Seer",
    ]
    
    for area_name in areas:
        existing = db.query(Area).filter(
            Area.name.ilike(area_name),
            Area.city_id == amman.id
        ).first()
        if not existing:
            area = Area(name=area_name, city_id=amman.id, is_active=True)
            db.add(area)
            print(f"✓ Created area: {area_name} (Amman)")
        else:
            print(f"⊘ Area already exists: {area_name}")
    
    db.commit()


def seed_property_statuses(db: Session):
    """Seed property statuses."""
    statuses = [
        {"name": "Verified", "slug": "verified"},
        {"name": "Pending", "slug": "pending"},
        {"name": "Sold", "slug": "sold"},
        {"name": "Rented", "slug": "rented"},
        {"name": "Available", "slug": "available"},
    ]
    
    for status_data in statuses:
        existing = db.query(PropertyStatus).filter(
            PropertyStatus.slug == status_data["slug"]
        ).first()
        if not existing:
            status = PropertyStatus(**status_data, is_active=True)
            db.add(status)
            print(f"✓ Created status: {status_data['name']}")
        else:
            print(f"⊘ Status already exists: {status_data['name']}")
    
    db.commit()


def seed_features(db: Session):
    """Seed common property features."""
    features = [
        "Elevator",
        "Parking",
        "Maid's Room",
        "Laundry Room",
        "Storage Room",
        "Guard's Room",
        "Water Well",
        "Decorations",
        "Wall-Hung Toilets",
        "Jacuzzi",
        "Marble Floors",
        "Wall Closets",
        "Garden",
        "Swimming Pool",
        "Balcony",
        "Terrace",
        "Central Air Conditioning",
        "Split Units",
        "Underfloor Heating",
        "Radiators",
        "Fireplace",
        "Double Glazed Windows",
        "Window Shutters",
        "Electric",
        "Standard Doors",
        "Deluxe Finishing",
    ]
    
    for feature_name in features:
        slug = feature_name.lower().replace("'", "").replace(" ", "-").replace("/", "-")
        existing = db.query(Feature).filter(Feature.slug == slug).first()
        if not existing:
            feature = Feature(name=feature_name, slug=slug, is_active=True)
            db.add(feature)
            print(f"✓ Created feature: {feature_name}")
        else:
            print(f"⊘ Feature already exists: {feature_name}")
    
    db.commit()


def seed_search_fields(db: Session):
    """Seed search fields for filtering."""
    search_fields = [
        {"name": "Price", "field_key": "price", "field_type": "numeric", "is_range": True},
        {"name": "Bedrooms", "field_key": "bedrooms", "field_type": "integer", "is_range": False},
        {"name": "Bathrooms", "field_key": "bathrooms", "field_type": "integer", "is_range": False},
        {"name": "Area", "field_key": "area", "field_type": "numeric", "is_range": True},
        {"name": "City", "field_key": "city", "field_type": "string", "is_range": False},
        {"name": "Location", "field_key": "location", "field_type": "string", "is_range": False},
        {"name": "Property Type", "field_key": "property_type", "field_type": "string", "is_range": False},
        {"name": "Category", "field_key": "category", "field_type": "string", "is_range": False},
    ]
    
    for field_data in search_fields:
        existing = db.query(SearchField).filter(
            SearchField.field_key == field_data["field_key"]
        ).first()
        if not existing:
            field = SearchField(**field_data)
            db.add(field)
            print(f"✓ Created search field: {field_data['name']}")
        else:
            print(f"⊘ Search field already exists: {field_data['name']}")
    
    db.commit()


def seed_category_features(db: Session):
    """Link common features to categories."""
    # Get categories
    residential = db.query(PropertyCategory).filter(
        PropertyCategory.slug == "residential"
    ).first()
    commercial = db.query(PropertyCategory).filter(
        PropertyCategory.slug == "commercial"
    ).first()
    land = db.query(PropertyCategory).filter(
        PropertyCategory.slug == "land"
    ).first()
    
    # Get common features
    common_features = ["Elevator", "Parking", "Garden", "Swimming Pool"]
    
    for category in [residential, commercial]:
        if not category:
            continue
        for feature_name in common_features:
            feature = db.query(Feature).filter(Feature.name == feature_name).first()
            if feature:
                existing = db.query(CategoryFeature).filter(
                    CategoryFeature.category_id == category.id,
                    CategoryFeature.feature_id == feature.id
                ).first()
                if not existing:
                    cat_feature = CategoryFeature(
                        category_id=category.id,
                        feature_id=feature.id
                    )
                    db.add(cat_feature)
                    print(f"✓ Linked feature '{feature_name}' to category '{category.name}'")
    
    db.commit()


def seed_type_features(db: Session):
    """Link common features to property types."""
    # Get types
    apartment = db.query(PropertyType).filter(PropertyType.slug == "apartment").first()
    villa = db.query(PropertyType).filter(PropertyType.slug == "villa").first()
    
    # Features common to apartments
    apartment_features = ["Elevator", "Parking", "Balcony", "Central Air Conditioning"]
    # Features common to villas
    villa_features = ["Garden", "Swimming Pool", "Parking", "Maid's Room", "Guard's Room"]
    
    type_feature_map = {
        apartment: apartment_features if apartment else [],
        villa: villa_features if villa else [],
    }
    
    for prop_type, feature_names in type_feature_map.items():
        if not prop_type:
            continue
        for feature_name in feature_names:
            feature = db.query(Feature).filter(Feature.name == feature_name).first()
            if feature:
                existing = db.query(TypeFeature).filter(
                    TypeFeature.property_type_id == prop_type.id,
                    TypeFeature.feature_id == feature.id
                ).first()
                if not existing:
                    type_feature = TypeFeature(
                        property_type_id=prop_type.id,
                        feature_id=feature.id
                    )
                    db.add(type_feature)
                    print(f"✓ Linked feature '{feature_name}' to type '{prop_type.name}'")
    
    db.commit()


def seed_category_search_fields(db: Session):
    """Link search fields to categories."""
    # Get categories
    residential = db.query(PropertyCategory).filter(
        PropertyCategory.slug == "residential"
    ).first()
    commercial = db.query(PropertyCategory).filter(
        PropertyCategory.slug == "commercial"
    ).first()
    land = db.query(PropertyCategory).filter(
        PropertyCategory.slug == "land"
    ).first()
    
    # Get search fields
    price_field = db.query(SearchField).filter(SearchField.field_key == "price").first()
    bedrooms_field = db.query(SearchField).filter(SearchField.field_key == "bedrooms").first()
    area_field = db.query(SearchField).filter(SearchField.field_key == "area").first()
    city_field = db.query(SearchField).filter(SearchField.field_key == "city").first()
    
    # Link common fields to all categories
    for category in [residential, commercial, land]:
        if not category:
            continue
        for field in [price_field, area_field, city_field]:
            if field:
                existing = db.query(CategorySearchField).filter(
                    CategorySearchField.category_id == category.id,
                    CategorySearchField.field_id == field.id
                ).first()
                if not existing:
                    cat_search_field = CategorySearchField(
                        category_id=category.id,
                        field_id=field.id,
                        is_required=False
                    )
                    db.add(cat_search_field)
                    print(f"✓ Linked search field '{field.name}' to category '{category.name}'")
        
        # Bedrooms only for residential
        if category == residential and bedrooms_field:
            existing = db.query(CategorySearchField).filter(
                CategorySearchField.category_id == category.id,
                CategorySearchField.field_id == bedrooms_field.id
            ).first()
            if not existing:
                cat_search_field = CategorySearchField(
                    category_id=category.id,
                    field_id=bedrooms_field.id,
                    is_required=False
                )
                db.add(cat_search_field)
                print(f"✓ Linked search field 'Bedrooms' to category 'Residential'")
    
    db.commit()


def main():
    """Main function to seed all reference data."""
    print("=" * 60)
    print("Seeding Reference Data for Normalized Property Structure")
    print("=" * 60)
    print()
    
    db: Session = SessionLocal()
    try:
        print("1. Seeding Property Categories...")
        seed_categories(db)
        print()
        
        print("2. Seeding Property Types...")
        seed_property_types(db)
        print()
        
        print("3. Seeding Cities...")
        seed_cities(db)
        print()
        
        print("4. Seeding Areas...")
        seed_areas(db)
        print()
        
        print("5. Seeding Property Statuses...")
        seed_property_statuses(db)
        print()
        
        print("6. Seeding Features...")
        seed_features(db)
        print()
        
        print("7. Seeding Search Fields...")
        seed_search_fields(db)
        print()
        
        print("8. Linking Category Features...")
        seed_category_features(db)
        print()
        
        print("9. Linking Type Features...")
        seed_type_features(db)
        print()
        
        print("10. Linking Category Search Fields...")
        seed_category_search_fields(db)
        print()
        
        print("=" * 60)
        print("✓ Reference data seeding completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        db.rollback()
        print(f"✗ Error seeding data: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

