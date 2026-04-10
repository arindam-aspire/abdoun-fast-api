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
    
    existing_slugs = {
        slug for (slug,) in db.query(PropertyCategory.slug).all()
    }

    for cat_data in categories:
        existing = cat_data["slug"] in existing_slugs
        if not existing:
            category = PropertyCategory(**cat_data, is_active=True)
            db.add(category)
            print(f"Created category: {cat_data['name']}")
            existing_slugs.add(cat_data["slug"])
        else:
            print(f"Category already exists: {cat_data['name']}")
    
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
    
    existing_type_keys = {
        (slug, category_id)
        for slug, category_id in db.query(PropertyType.slug, PropertyType.category_id).all()
    }

    for type_data in types:
        category = type_data.pop("category")
        if not category:
            continue

        type_key = (type_data["slug"], category.id)
        existing = type_key in existing_type_keys
        if not existing:
            prop_type = PropertyType(**type_data, category_id=category.id, is_active=True)
            db.add(prop_type)
            print(f"Created type: {type_data['name']} ({category.name})")
            existing_type_keys.add(type_key)
        else:
            print(f"Type already exists: {type_data['name']}")
    
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
    
    existing_city_names = {
        (name or "").strip().lower() for (name,) in db.query(City.name).all()
    }

    for city_data in cities:
        city_key = city_data["name"].strip().lower()
        existing = city_key in existing_city_names
        if not existing:
            city = City(**city_data, is_active=True)
            db.add(city)
            print(f"Created city: {city_data['name']}")
            existing_city_names.add(city_key)
        else:
            print(f"City already exists: {city_data['name']}")
    
    db.commit()


def seed_areas(db: Session):
    """Seed areas for Amman."""
    amman = db.query(City).filter(City.name.ilike("Amman")).first()
    if not amman:
        print("Amman city not found. Creating it first...")
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
    
    existing_areas = {
        (name or "").strip().lower()
        for (name,) in db.query(Area.name).filter(Area.city_id == amman.id).all()
    }

    for area_name in areas:
        area_key = area_name.strip().lower()
        existing = area_key in existing_areas
        if not existing:
            area = Area(name=area_name, city_id=amman.id, is_active=True)
            db.add(area)
            print(f"Created area: {area_name} (Amman)")
            existing_areas.add(area_key)
        else:
            print(f"Area already exists: {area_name}")
    
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
    
    existing_status_slugs = {
        slug for (slug,) in db.query(PropertyStatus.slug).all()
    }

    for status_data in statuses:
        existing = status_data["slug"] in existing_status_slugs
        if not existing:
            status = PropertyStatus(**status_data, is_active=True)
            db.add(status)
            print(f"Created status: {status_data['name']}")
            existing_status_slugs.add(status_data["slug"])
        else:
            print(f"Status already exists: {status_data['name']}")
    
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
    
    existing_feature_slugs = {
        slug for (slug,) in db.query(Feature.slug).all()
    }

    for feature_name in features:
        slug = feature_name.lower().replace("'", "").replace(" ", "-").replace("/", "-")
        existing = slug in existing_feature_slugs
        if not existing:
            feature = Feature(name=feature_name, slug=slug, is_active=True)
            db.add(feature)
            print(f"Created feature: {feature_name}")
            existing_feature_slugs.add(slug)
        else:
            print(f"Feature already exists: {feature_name}")
    
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
    
    existing_field_keys = {
        key for (key,) in db.query(SearchField.field_key).all()
    }

    for field_data in search_fields:
        existing = field_data["field_key"] in existing_field_keys
        if not existing:
            field = SearchField(**field_data)
            db.add(field)
            print(f"Created search field: {field_data['name']}")
            existing_field_keys.add(field_data["field_key"])
        else:
            print(f"Search field already exists: {field_data['name']}")
    
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
    features_by_name = {
        name: feat
        for name, feat in (
            db.query(Feature.name, Feature).all()
        )
    }
    existing_pairs = {
        (category_id, feature_id)
        for category_id, feature_id in db.query(CategoryFeature.category_id, CategoryFeature.feature_id).all()
    }
    
    for category in [residential, commercial]:
        if not category:
            continue
        for feature_name in common_features:
            feature = features_by_name.get(feature_name)
            if feature:
                pair = (category.id, feature.id)
                if pair not in existing_pairs:
                    cat_feature = CategoryFeature(
                        category_id=category.id,
                        feature_id=feature.id
                    )
                    db.add(cat_feature)
                    print(f"Linked feature '{feature_name}' to category '{category.name}'")
                    existing_pairs.add(pair)
    
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
    features_by_name = {
        name: feat
        for name, feat in (
            db.query(Feature.name, Feature).all()
        )
    }
    existing_pairs = {
        (type_id, feature_id)
        for type_id, feature_id in db.query(TypeFeature.property_type_id, TypeFeature.feature_id).all()
    }
    
    type_feature_map = {
        apartment: apartment_features if apartment else [],
        villa: villa_features if villa else [],
    }
    
    for prop_type, feature_names in type_feature_map.items():
        if not prop_type:
            continue
        for feature_name in feature_names:
            feature = features_by_name.get(feature_name)
            if feature:
                pair = (prop_type.id, feature.id)
                if pair not in existing_pairs:
                    type_feature = TypeFeature(
                        property_type_id=prop_type.id,
                        feature_id=feature.id
                    )
                    db.add(type_feature)
                    print(f"Linked feature '{feature_name}' to type '{prop_type.name}'")
                    existing_pairs.add(pair)
    
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
    
    existing_pairs = {
        (category_id, field_id)
        for category_id, field_id in db.query(CategorySearchField.category_id, CategorySearchField.field_id).all()
    }

    # Link common fields to all categories
    for category in [residential, commercial, land]:
        if not category:
            continue
        for field in [price_field, area_field, city_field]:
            if field:
                pair = (category.id, field.id)
                if pair not in existing_pairs:
                    cat_search_field = CategorySearchField(
                        category_id=category.id,
                        field_id=field.id,
                        is_required=False
                    )
                    db.add(cat_search_field)
                    print(f"Linked search field '{field.name}' to category '{category.name}'")
                    existing_pairs.add(pair)
        
        # Bedrooms only for residential
        if category == residential and bedrooms_field:
            pair = (category.id, bedrooms_field.id)
            if pair not in existing_pairs:
                cat_search_field = CategorySearchField(
                    category_id=category.id,
                    field_id=bedrooms_field.id,
                    is_required=False
                )
                db.add(cat_search_field)
                print(f"Linked search field 'Bedrooms' to category 'Residential'")
                existing_pairs.add(pair)
    
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
        print("Reference data seeding completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        db.rollback()
        print(f"Error seeding data: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

