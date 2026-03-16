# Property API Response Format Transformation Guide

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current vs New Format Comparison](#current-vs-new-format-comparison)
3. [Field-by-Field Analysis](#field-by-field-analysis)
4. [Data Collection from CSV](#data-collection-from-csv)
5. [Database Schema Changes](#database-schema-changes)
6. [Transformation Implementation](#transformation-implementation)
7. [Migration Strategy](#migration-strategy)
8. [Effectiveness & Recommendations](#effectiveness--recommendations)

---

## Executive Summary

This document provides a comprehensive guide for transforming the current property API response format to a new structured format with:

- **Multi-language support** (English & Arabic)
- **Nested object structure** for better organization
- **Rich metadata** (agent, owner, media management)
- **Enhanced property details** (general, details, features, pricing)
- **SEO-friendly slugs** for better discoverability

**Key Statistics:**
- **~70% of fields** can be extracted directly or derived from existing CSV
- **~20% of fields** require translation or external data (Arabic translations)
- **~10% of fields** are completely missing and need manual input or defaults

**Recommended Approach:** Incremental migration in phases, starting with structure transformation and multi-language support.

---

## Current vs New Format Comparison

### Current Format

#### Property List Response (`GET /api/v1/properties`)
```json
{
  "data": [
    {
      "id": 335889075,
      "title": "Semi Villa for Sale / Rent",
      "price": "450,000 JOD",
      "status": "buy",
      "category": "residential",
      "searchPropertyType": "Villas",
      "city": "Amman",
      "areaName": "Abdoun",
      "propertyType": "Villa",
      "images": ["url1", "url2"],
      "location": "Abdoun - Amman",
      "beds": 4,
      "baths": 7,
      "area": "500",
      "highlights": "4BHK | Residential",
      "badges": ["For Sale", "For Rent", "Verified"]
    }
  ],
  "total": 100,
  "page": 1,
  "pageSize": 12
}
```

#### Property Detail Response (`GET /api/v1/properties/{id}`)
```json
{
  "id": 335889075,
  "url": "https://...",
  "title": "Semi Villa for Sale / Rent",
  "description": "...",
  "category": "Villa",
  "status": "For Sale",
  "selling_price_amount": 450000.00,
  "selling_price_currency": "JOD",
  "rent_price_amount": 35000.00,
  "rent_price_currency": "JOD",
  "bedrooms": 4,
  "bathrooms": 7,
  "built_up_area": 500.0,
  "features": ["maid_room", "elevator"],
  "more_features": {
    "Finishing": "Deluxe",
    "Windows": "Double Glazed"
  },
  "images": ["url1", "url2"],
  "latitude": 31.9654,
  "longitude": 35.8701,
  "location_name": "Abdoun - Amman"
}
```

### New Format (Target)

```json
{
  "id": 6281,
  "reference_number": "06281",
  "status": "active",
  "listing_type": "rent",
  "property_type": "apartment",
  "category": "residential",
  "is_exclusive": true,
  "title": {
    "en": "Apartment for Rent",
    "ar": "شقة للإيجار"
  },
  "description": {
    "en": "Spacious furnished apartment in the heart of Dair Gbhar...",
    "ar": "شقة مفروشة واسعة في قلب دير غبار..."
  },
  "slug": {
    "en": "apartment-for-rent-dair-gbhar-06281",
    "ar": "شقة-للإيجار-دير-غبار-06281"
  },
  "location": {
    "country_id": 1,
    "country": "Jordan",
    "city_id": 5,
    "city": "Amman",
    "region_id": 12,
    "region": "Dair Gbhar",
    "address": {
      "en": "Dair Gbhar - Amman",
      "ar": "دير غبار - عمان"
    },
    "latitude": 31.9654,
    "longitude": 35.8701,
    "map_embed_url": "https://maps.google.com/?q=31.9654,35.8701"
  },
  "general": {
    "floor_type": "ground",
    "floor_number": 0,
    "building_status": "used",
    "built_in_year": 2000,
    "furniture_status": "furnished",
    "furniture_condition": "good_condition",
    "garage_type": "closed",
    "total_floors_in_building": 6
  },
  "details": {
    "built_up_area": 314,
    "land_area": null,
    "garden_area": 50,
    "area_unit": "sqm",
    "bedrooms": 4,
    "master_bedrooms": 2,
    "bathrooms": 4,
    "living_rooms": 1,
    "salons": 1,
    "balconies": 1,
    "entrances": 3,
    "kitchens": 1,
    "kitchen_type": "installed",
    "maid_rooms": 1,
    "driver_rooms": 0,
    "store_rooms": 1
  },
  "features": {
    "amenities": ["maid_room", "laundry_room", "storage_room", "elevator"],
    "finishing": "deluxe",
    "windows": "double_glazed",
    "window_shutters": "manual",
    "doors": "standard",
    "air_conditioning": "split_units",
    "heating_system": "underfloor",
    "heating_fuel": "diesel",
    "has_view": true,
    "view_type": ["city_view", "garden_view"]
  },
  "pricing": {
    "listing_type": "rent",
    "annual_rent": 35000,
    "monthly_rent": null,
    "quarterly_rent": null,
    "selling_price": null,
    "currency": "JOD",
    "price_on_request": false,
    "rent_commission_percent": 5.00,
    "contract_duration": null,
    "contract_duration_unit": null,
    "payment_method": "annual",
    "is_negotiable": false,
    "down_payment": null,
    "installment_available": false,
    "installment_details": null
  },
  "media": {
    "thumbnail": "https://cdn.example.com/properties/6281/thumb.jpeg",
    "images": [
      {
        "id": 1,
        "url": "https://cdn.example.com/properties/6281/img1.jpeg",
        "thumb_url": "https://cdn.example.com/properties/6281/img1-thumb.jpeg",
        "is_primary": true,
        "order": 1,
        "caption": null
      }
    ],
    "videos": [],
    "virtual_tour_url": null,
    "floor_plan_images": [],
    "documents": []
  },
  "agent": {
    "id": 3,
    "name": "Ahmed Al-Khalidi",
    "phone": "+962799000000",
    "whatsapp": "+962799000000",
    "email": "ahmed@example.com",
    "photo": "https://cdn.example.com/agents/3/photo.jpg",
    "license_number": "RE-0042"
  },
  "owner": {
    "id": 55,
    "name": "Mohammad Tarawneh",
    "phone": "+962790000000",
    "email": "owner@example.com",
    "is_private": false
  },
  "created_by": {
    "id": 2,
    "name": "Admin Sarah",
    "role": "super_admin"
  },
  "created_at": "2023-08-16T10:20:00Z",
  "updated_at": "2024-01-10T08:00:00Z",
  "published_at": "2023-08-16T12:00:00Z",
  "expires_at": null,
  "sold_at": null,
  "rented_at": null
}
```

---

## Field-by-Field Analysis

### Available in Current Database/API

| Field | Current Location | Notes |
|-------|-----------------|-------|
| `id` | `PropertyNormalized.id` | UUID, converted to int hash |
| `is_exclusive` | `PropertyNormalized.is_exclusive` | Boolean field exists |
| `title` | `PropertyNormalized.title` | Single language (English) |
| `description` | `PropertyNormalized.description` | Single language |
| `category` | `PropertyNormalized.category.name` | Via relationship |
| `property_type` | `PropertyNormalized.type.name` | Via relationship |
| `listing_type` | Derived from `selling_price_amount` / `rent_price_amount` | Can infer from prices |
| `city_id` | `PropertyNormalized.city_id` | Foreign key exists |
| `city` | `PropertyNormalized.city.name` | Via relationship |
| `region_id` | `PropertyNormalized.location_id` | This is area_id |
| `region` | `PropertyNormalized.area_rel.name` | Via relationship |
| `latitude` | `PropertyNormalized.latitude` | DECIMAL field |
| `longitude` | `PropertyNormalized.longitude` | DECIMAL field |
| `bedrooms` | `PropertyNormalized.bedrooms` | Integer field |
| `bathrooms` | `PropertyNormalized.bathrooms` | Integer field |
| `built_up_area` | `PropertyNormalized.area` | Numeric field |
| `land_area` | `PropertyNormalized.plot_area` | Numeric field |
| `furniture_status` | `PropertyNormalized.furniture_status` | String field |
| `selling_price` | `PropertyNormalized.selling_price_amount` | Numeric field |
| `rent_price` | `PropertyNormalized.rent_price_amount` | Numeric field |
| `currency` | `PropertyNormalized.selling_price_currency` / `rent_price_currency` | String field |
| `features` | `PropertyNormalized.features` (relationship) | Via PropertyFeature |
| `more_features` | `PropertyNormalized.more_features` (JSONB) | Key-value pairs |
| `images` | `PropertyNormalized.images` (JSON string) | Array of URLs |
| `created_at` | `PropertyNormalized.created_at` | TIMESTAMP |
| `updated_at` | `PropertyNormalized.updated_at` | TIMESTAMP |

### Missing in Current Database/API

| Field | Required For | Impact Level | Solution |
|-------|-------------|--------------|----------|
| `reference_number` | Top-level | **HIGH** | Extract from CSV `property_id` or generate |
| `status` | Top-level | **MEDIUM** | Map `property_status.name` → "active"/"inactive" |
| `title.ar` / `description.ar` | Multi-language | **HIGH** | Translation API or manual translation |
| `slug.en` / `slug.ar` | SEO | **MEDIUM** | Generate from title (slugify) |
| `country_id` / `country` | Location | **MEDIUM** | Hardcode: 1 (Jordan) |
| `address.ar` | Location | **LOW** | Translation needed |
| `map_embed_url` | Location | **LOW** | Generate from lat/lng |
| `floor_type` / `floor_number` | General | **MEDIUM** | Parse from CSV `type` and `floor` |
| `building_status` | General | **MEDIUM** | Parse from CSV `building_status` |
| `built_in_year` | General | **MEDIUM** | Calculate from `property_age` if available |
| `garden_area` | Details | **MEDIUM** | Parse from CSV `garden_area` |
| `master_bedrooms` | Details | **MEDIUM** | Parse from CSV `master_bedrooms` |
| `living_rooms` / `salons` / `balconies` | Details | **MEDIUM** | Not in CSV - default to NULL or 1 |
| `maid_rooms` / `driver_rooms` / `store_rooms` | Details | **MEDIUM** | Extract from `features` list |
| `features.finishing` / `features.windows` | Features | **MEDIUM** | Extract from `more_features` JSON |
| `pricing.monthly_rent` / `quarterly_rent` | Pricing | **MEDIUM** | Calculate from `annual_rent` |
| `pricing.rent_commission_percent` | Pricing | **LOW** | Parse from CSV `rent_commission` |
| `media.images[].id` / `is_primary` / `order` | Media | **MEDIUM** | Transform images array to objects |
| `agent` | Agent | **HIGH** | Requires separate agent management system |
| `owner` | Owner | **HIGH** | Requires separate owner management system |
| `created_by` | Metadata | **MEDIUM** | Requires user management system |
| `published_at` | Metadata | **MEDIUM** | Use `created_at` as fallback |

---

## Data Collection from CSV

### CSV Column Structure

The current CSV (`abdoun_merged_properties.csv`) contains:
```
url, property_name, category, location, selling_price, rent_price, type, floor, 
building_status, furniture, garage, built_up_area, garden_area, terrace_area, 
area_sqm, bedrooms, master_bedrooms, bathrooms, kitchens, rent_commission, 
contract_duration, payment_method, property_id, description, features, 
more_features, image_urls, status, latitude, longitude
```

### Complete Field Mapping: CSV → New Format

#### 1. Top-Level Fields

| New Format Field | CSV Source | Transformation Logic | Status |
|-----------------|------------|---------------------|--------|
| `id` | `property_id` | Use existing UUID hash or generate from `property_id` | Direct |
| `reference_number` | `property_id` | Format: `property_id` (e.g., "01002" → "01002") | Direct |
| `status` | `status` | Map: "ok" → "active", else → "pending" | Direct |
| `listing_type` | `selling_price`, `rent_price` | If both exist → "both", else "rent" or "buy" | Derived |
| `property_type` | `category`, `type` | Extract from category/type (e.g., "Apartment", "Villa") | Derived |
| `category` | `category` | Map to: "residential", "commercial", "land" | Derived |
| `is_exclusive` | Calculated | From existing `is_exclusive` column in DB | Direct |

#### 2. Multi-Language Fields

| New Format Field | CSV Source | Transformation Logic | Status |
|-----------------|------------|---------------------|--------|
| `title.en` | `property_name` | Direct copy | Direct |
| `title.ar` | `property_name` | **Translation API or manual translation** | Missing |
| `description.en` | `description` | Direct copy | Direct |
| `description.ar` | `description` | **Translation API or manual translation** | Missing |
| `slug.en` | `property_name`, `location`, `property_id` | Generate: `slugify(property_name + location + property_id)` | Derived |
| `slug.ar` | `property_name`, `location`, `property_id` | Generate from Arabic title | Missing |
| `address.en` | `location` | Direct copy (e.g., "Dabouq - Amman") | Direct |
| `address.ar` | `location` | **Translation API or manual translation** | Missing |

#### 3. Location Fields

| New Format Field | CSV Source | Transformation Logic | Status |
|-----------------|------------|---------------------|--------|
| `country_id` | N/A | Default to 1 (Jordan) | Default |
| `country` | N/A | Default to "Jordan" | Default |
| `city_id` | `location` | Extract city from "Area - City" format, lookup/create in DB | Derived |
| `city` | `location` | Extract city name (e.g., "Amman") | Derived |
| `region_id` | `location` | Extract area from "Area - City" format, lookup/create in DB | Derived |
| `region` | `location` | Extract area name (e.g., "Dabouq") | Derived |
| `latitude` | `latitude` | Direct copy | Direct |
| `longitude` | `longitude` | Direct copy | Direct |
| `map_embed_url` | `latitude`, `longitude` | Generate: `https://maps.google.com/?q={lat},{lng}` | Derived |

#### 4. General Details

| New Format Field | CSV Source | Transformation Logic | Status |
|-----------------|------------|---------------------|--------|
| `floor_type` | `type` | Map: "Ground" → "ground", "Upper Floor" → "upper", "Semi Ground Floor" → "semi_ground", "Roof" → "roof" | Derived |
| `floor_number` | `floor` | Parse float to int (e.g., 1.0 → 1, -1.0 → -1) | Direct |
| `building_status` | `building_status` | Map: "Used" → "used", "New" → "new", else → "used" | Direct |
| `built_in_year` | N/A | **Not in CSV** - Set to NULL or estimate from `building_status` | Missing |
| `furniture_status` | `furniture` | Map: "Furnished" → "furnished", "Unfurnished" → "unfurnished" | Direct |
| `furniture_condition` | N/A | **Not in CSV** - Default to NULL | Missing |
| `garage_type` | `garage` | Map: "Closed" → "closed", "Open" → "open", empty → NULL | Direct |
| `total_floors_in_building` | N/A | **Not in CSV** - Set to NULL | Missing |

#### 5. Property Details

| New Format Field | CSV Source | Transformation Logic | Status |
|-----------------|------------|---------------------|--------|
| `built_up_area` | `built_up_area` or `area_sqm` | Parse "400 Sqm" → 400.0 | Direct |
| `land_area` | `plot_area` (from DB) | Use `plot_area` if available | From DB |
| `garden_area` | `garden_area` | Parse "50 Sqm" → 50.0 | Direct |
| `area_unit` | N/A | Default to "sqm" | Default |
| `bedrooms` | `bedrooms` | Direct copy | Direct |
| `master_bedrooms` | `master_bedrooms` | Parse "1.0" → 1 | Direct |
| `bathrooms` | `bathrooms` | Parse "4.0" → 4 | Direct |
| `living_rooms` | N/A | **Not in CSV** - Default to 1 or NULL | Missing |
| `salons` | N/A | **Not in CSV** - Default to 1 or NULL | Missing |
| `balconies` | N/A | **Not in CSV** - Default to NULL | Missing |
| `entrances` | N/A | **Not in CSV** - Default to NULL | Missing |
| `kitchens` | `kitchens` | Parse "1.0" → 1 | Direct |
| `kitchen_type` | N/A | **Not in CSV** - Default to "installed" or NULL | Missing |
| `maid_rooms` | `features` | Extract from features: "Maid's Room" → 1, else → 0 | Derived |
| `driver_rooms` | `features` | Extract from features: "Driver's Room" → 1, else → 0 | Derived |
| `store_rooms` | `features` | Extract from features: "Storage Room" → 1, else → 0 | Derived |

#### 6. Features Structure

| New Format Field | CSV Source | Transformation Logic | Status |
|-----------------|------------|---------------------|--------|
| `amenities` | `features` | Parse pipe-separated: "Maid's Room\|Elevator\|..." → ["maid_room", "elevator", ...] | Derived |
| `finishing` | `more_features` | Extract from key-value: "Finishing\|Deluxe" → "deluxe" | Derived |
| `windows` | `more_features` | Extract: "Windows\|Double Glazed" → "double_glazed" | Derived |
| `window_shutters` | `more_features` | Extract: "Window Shutters\|Electric" → "electric" | Derived |
| `doors` | `more_features` | Extract: "Doors\|Standard" → "standard" | Derived |
| `air_conditioning` | `more_features` | Extract: "Air Conditioning\|Central" → "central" | Derived |
| `heating_system` | `more_features` | Extract: "Heating System\|Central" → "central" | Derived |
| `heating_fuel` | `more_features` | Extract: "Heating Fuel\|Diesel" → "diesel" | Derived |
| `has_view` | N/A | **Not in CSV** - Default to false | Missing |
| `view_type` | N/A | **Not in CSV** - Default to [] | Missing |

**CSV `more_features` Format:**
- Pipe-separated key-value pairs: `Finishing|Deluxe|Windows|Double Glazed|Window Shutters|Electric`
- Transform to: `{"Finishing": "Deluxe", "Windows": "Double Glazed", "Window Shutters": "Electric"}`

**CSV `features` Format:**
- Pipe-separated list: `Maid's Room|Laundry Room|Storage Room|Elevator`
- Transform to: `["maid_room", "laundry_room", "storage_room", "elevator"]` (normalize to slugs)

#### 7. Pricing Details

| New Format Field | CSV Source | Transformation Logic | Status |
|-----------------|------------|---------------------|--------|
| `listing_type` | `selling_price`, `rent_price` | If both → "both", else "rent" or "buy" | Derived |
| `annual_rent` | `rent_price` | Parse "30,000 JOD" → 30000.0 | Direct |
| `monthly_rent` | `rent_price` | Calculate: `annual_rent / 12` | Derived |
| `quarterly_rent` | `rent_price` | Calculate: `annual_rent / 4` | Derived |
| `selling_price` | `selling_price` | Parse "320,000 JOD" → 320000.0 | Direct |
| `currency` | `rent_price` or `selling_price` | Extract currency (default: "JOD") | Derived |
| `price_on_request` | N/A | Default to false | Default |
| `rent_commission_percent` | `rent_commission` | Parse "5.00 %" → 5.00 | Direct |
| `contract_duration` | `contract_duration` | Parse if available, else NULL | Direct |
| `contract_duration_unit` | `contract_duration` | Infer from value, else NULL | Derived |
| `payment_method` | `payment_method` | Map: "Annual" → "annual", etc. | Direct |
| `is_negotiable` | N/A | Default to false | Default |
| `down_payment` | N/A | **Not in CSV** - Default to NULL | Missing |
| `installment_available` | N/A | **Not in CSV** - Default to false | Missing |
| `installment_details` | N/A | **Not in CSV** - Default to NULL | Missing |

#### 8. Media Structure

| New Format Field | CSV Source | Transformation Logic | Status |
|-----------------|------------|---------------------|--------|
| `thumbnail` | `image_urls` | Use first image URL | Derived |
| `images[].id` | `image_urls` | Generate sequential IDs (1, 2, 3, ...) | Derived |
| `images[].url` | `image_urls` | Parse pipe-separated URLs | Derived |
| `images[].thumb_url` | `image_urls` | Use same URL (thumbnails already in CSV) | Derived |
| `images[].is_primary` | `image_urls` | First image → true, others → false | Derived |
| `images[].order` | `image_urls` | Sequential order (1, 2, 3, ...) | Derived |
| `images[].caption` | N/A | Default to NULL | Default |
| `videos` | N/A | **Not in CSV** - Default to [] | Missing |
| `virtual_tour_url` | N/A | **Not in CSV** - Default to NULL | Missing |
| `floor_plan_images` | N/A | **Not in CSV** - Default to [] | Missing |
| `documents` | N/A | **Not in CSV** - Default to [] | Missing |

#### 9. Agent & Owner

| New Format Field | CSV Source | Transformation Logic | Status |
|-----------------|------------|---------------------|--------|
| `agent` | N/A | **Not in CSV** - Default to NULL or create default agent | Missing |
| `owner` | N/A | **Not in CSV** - Default to NULL | Missing |

#### 10. Metadata

| New Format Field | CSV Source | Transformation Logic | Status |
|-----------------|------------|---------------------|--------|
| `created_by` | N/A | **Not in CSV** - Default to system user | Missing |
| `created_at` | DB `created_at` | Use existing timestamp | From DB |
| `updated_at` | DB `updated_at` | Use existing timestamp | From DB |
| `published_at` | `status` | If status="ok" → use `created_at`, else NULL | Derived |
| `expires_at` | N/A | **Not in CSV** - Default to NULL | Missing |
| `sold_at` | N/A | **Not in CSV** - Default to NULL | Missing |
| `rented_at` | N/A | **Not in CSV** - Default to NULL | Missing |

---

## Database Schema Changes

### 1. Multi-Language Support Tables

```sql
-- Property translations
CREATE TABLE property_translations (
    id SERIAL PRIMARY KEY,
    property_id UUID REFERENCES properties_normalized(id) ON DELETE CASCADE,
    language_code VARCHAR(5) NOT NULL, -- 'en', 'ar'
    title TEXT,
    description TEXT,
    slug VARCHAR(255),
    address TEXT,
    UNIQUE(property_id, language_code)
);

-- Index for slug lookups
CREATE INDEX idx_property_translations_slug ON property_translations(slug);
CREATE INDEX idx_property_translations_property_id ON property_translations(property_id);
```

### 2. Countries Table

```sql
CREATE TABLE countries (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(2) NOT NULL UNIQUE, -- ISO country code
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Add country_id to properties_normalized
ALTER TABLE properties_normalized 
ADD COLUMN country_id INTEGER REFERENCES countries(id) DEFAULT 1;
```

### 3. Property General Details

```sql
ALTER TABLE properties_normalized
ADD COLUMN floor_type VARCHAR(50), -- 'ground', 'first', 'second', etc.
ADD COLUMN floor_number INTEGER,
ADD COLUMN building_status VARCHAR(50), -- 'new', 'used', 'under_construction'
ADD COLUMN built_in_year INTEGER,
ADD COLUMN furniture_condition VARCHAR(50), -- 'excellent', 'good', 'fair', 'poor'
ADD COLUMN garage_type VARCHAR(50), -- 'open', 'closed', 'covered'
ADD COLUMN total_floors_in_building INTEGER;
```

### 4. Property Details Extension

```sql
ALTER TABLE properties_normalized
ADD COLUMN garden_area NUMERIC(10, 2),
ADD COLUMN area_unit VARCHAR(10) DEFAULT 'sqm',
ADD COLUMN master_bedrooms INTEGER,
ADD COLUMN living_rooms INTEGER,
ADD COLUMN salons INTEGER,
ADD COLUMN balconies INTEGER,
ADD COLUMN entrances INTEGER,
ADD COLUMN kitchens INTEGER,
ADD COLUMN kitchen_type VARCHAR(50), -- 'installed', 'not_installed'
ADD COLUMN maid_rooms INTEGER,
ADD COLUMN driver_rooms INTEGER,
ADD COLUMN store_rooms INTEGER;
```

### 5. Features Structure Enhancement

```sql
-- Add specific feature fields (can extract from more_features JSON)
ALTER TABLE properties_normalized
ADD COLUMN finishing VARCHAR(50), -- Extract from more_features
ADD COLUMN windows VARCHAR(50), -- Extract from more_features
ADD COLUMN window_shutters VARCHAR(50), -- Extract from more_features
ADD COLUMN doors VARCHAR(50),
ADD COLUMN air_conditioning VARCHAR(50), -- Extract from more_features
ADD COLUMN heating_system VARCHAR(50), -- Extract from more_features
ADD COLUMN heating_fuel VARCHAR(50),
ADD COLUMN has_view BOOLEAN DEFAULT FALSE,
ADD COLUMN view_type JSONB; -- Array of view types
```

### 6. Pricing Details

```sql
ALTER TABLE properties_normalized
ADD COLUMN monthly_rent NUMERIC(15, 2),
ADD COLUMN quarterly_rent NUMERIC(15, 2),
ADD COLUMN price_on_request BOOLEAN DEFAULT FALSE,
ADD COLUMN rent_commission_percent NUMERIC(5, 2),
ADD COLUMN contract_duration INTEGER,
ADD COLUMN contract_duration_unit VARCHAR(20), -- 'month', 'year'
ADD COLUMN payment_method VARCHAR(20), -- 'monthly', 'quarterly', 'annual'
ADD COLUMN is_negotiable BOOLEAN DEFAULT FALSE,
ADD COLUMN down_payment NUMERIC(15, 2),
ADD COLUMN installment_available BOOLEAN DEFAULT FALSE,
ADD COLUMN installment_details JSONB;
```

### 7. Media Management

```sql
-- Property images table
CREATE TABLE property_images (
    id SERIAL PRIMARY KEY,
    property_id UUID REFERENCES properties_normalized(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    thumb_url TEXT,
    is_primary BOOLEAN DEFAULT FALSE,
    display_order INTEGER DEFAULT 0,
    caption TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_property_images_property_id ON property_images(property_id);
CREATE INDEX idx_property_images_primary ON property_images(property_id, is_primary);

-- Property videos
CREATE TABLE property_videos (
    id SERIAL PRIMARY KEY,
    property_id UUID REFERENCES properties_normalized(id) ON DELETE CASCADE,
    type VARCHAR(20) NOT NULL, -- 'youtube', 'vimeo', 'direct'
    url TEXT NOT NULL,
    thumbnail TEXT,
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Property documents
CREATE TABLE property_documents (
    id SERIAL PRIMARY KEY,
    property_id UUID REFERENCES properties_normalized(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL, -- 'title_deed', 'contract', 'permit', etc.
    file_url TEXT NOT NULL,
    label VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE properties_normalized
ADD COLUMN virtual_tour_url TEXT;
```

### 8. Agent and Owner Management

```sql
-- Agents table
CREATE TABLE agents (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    whatsapp VARCHAR(20),
    email VARCHAR(255),
    photo TEXT,
    license_number VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Owners table
CREATE TABLE owners (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    email VARCHAR(255),
    is_private BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Add foreign keys to properties
ALTER TABLE properties_normalized
ADD COLUMN agent_id INTEGER REFERENCES agents(id),
ADD COLUMN owner_id INTEGER REFERENCES owners(id);
```

### 9. Metadata Fields

```sql
ALTER TABLE properties_normalized
ADD COLUMN reference_number VARCHAR(50) UNIQUE,
ADD COLUMN status VARCHAR(20) DEFAULT 'active', -- 'active', 'inactive', 'sold', 'rented'
ADD COLUMN created_by_id INTEGER, -- References users table (if exists)
ADD COLUMN published_at TIMESTAMP,
ADD COLUMN expires_at TIMESTAMP,
ADD COLUMN sold_at TIMESTAMP,
ADD COLUMN rented_at TIMESTAMP;

-- Index for reference_number lookups
CREATE INDEX idx_properties_reference_number ON properties_normalized(reference_number);
CREATE INDEX idx_properties_status ON properties_normalized(status);
```

---

## Transformation Implementation

### Python Transformation Function

```python
from typing import Optional
from app.models.property_normalized import PropertyNormalized as Property
from app.schemas.property import uuid_to_int_hash
import json
import re

def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip('-')

def parse_more_features(more_features_str: str) -> dict:
    """Parse pipe-separated key-value pairs to dictionary."""
    if not more_features_str:
        return {}
    
    parts = more_features_str.split('|')
    result = {}
    for i in range(0, len(parts) - 1, 2):
        key = parts[i].strip()
        value = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if key:
            result[key] = value
    return result

def normalize_feature_name(feature_name: str) -> str:
    """Normalize feature name to slug format."""
    return slugify(feature_name.replace("'s", "").replace("'", ""))

def parse_price(price_str: str) -> Optional[float]:
    """Parse price string like 'JOD 320,000' or '30,000 JOD' to float."""
    if not price_str:
        return None
    # Remove currency and commas
    numbers = re.sub(r'[^\d.]', '', price_str)
    try:
        return float(numbers)
    except:
        return None

def parse_area(area_str: str) -> Optional[float]:
    """Parse area string like '400 Sqm' to float."""
    if not area_str:
        return None
    numbers = re.sub(r'[^\d.]', '', area_str)
    try:
        return float(numbers)
    except:
        return None

def determine_listing_type(property: Property) -> str:
    """Determine listing type from prices."""
    has_selling = property.selling_price_amount is not None
    has_rent = property.rent_price_amount is not None
    
    if has_selling and has_rent:
        return "both"
    elif has_selling:
        return "buy"
    elif has_rent:
        return "rent"
    else:
        return "unknown"

def transform_property_to_new_format(property: Property, lang: str = "en") -> dict:
    """
    Transform PropertyNormalized object to new API response format.
    
    Args:
        property: PropertyNormalized ORM object
        lang: Language code ('en' or 'ar')
    
    Returns:
        Dictionary matching new API response format
    """
    # Parse images
    images_list = []
    if property.images:
        try:
            images_list = json.loads(property.images) if isinstance(property.images, str) else property.images
        except:
            images_list = []
    
    # Parse more_features
    more_features = property.more_features if hasattr(property, 'more_features') and property.more_features else {}
    
    # Get features list
    amenities = []
    if property.features:
        amenities = [normalize_feature_name(f.feature.name) for f in property.features if f.feature]
    
    # Extract room counts from features
    feature_names = [f.feature.name.lower() if f.feature else "" for f in property.features] if property.features else []
    maid_rooms = 1 if any("maid" in f for f in feature_names) else 0
    driver_rooms = 1 if any("driver" in f for f in feature_names) else 0
    store_rooms = 1 if any("storage" in f or "store" in f for f in feature_names) else 0
    
    # Calculate derived pricing
    annual_rent = float(property.rent_price_amount) if property.rent_price_amount else None
    monthly_rent = annual_rent / 12 if annual_rent else None
    quarterly_rent = annual_rent / 4 if annual_rent else None
    
    # Build response
    result = {
        "id": uuid_to_int_hash(property.id) if isinstance(property.id, uuid.UUID) else property.id,
        "reference_number": getattr(property, 'reference_number', None) or f"{uuid_to_int_hash(property.id):05d}",
        "status": getattr(property, 'status', 'active') or 'active',
        "listing_type": determine_listing_type(property),
        "property_type": property.type.slug if property.type else None,
        "category": property.category.slug if property.category else None,
        "is_exclusive": property.is_exclusive,
        
        # Bilingual content (use English as fallback for Arabic)
        "title": {
            "en": property.title or "",
            "ar": getattr(property, 'title_ar', None) or property.title or ""
        },
        "description": {
            "en": property.description or "",
            "ar": getattr(property, 'description_ar', None) or property.description or ""
        },
        "slug": {
            "en": getattr(property, 'slug_en', None) or slugify(property.title or ""),
            "ar": getattr(property, 'slug_ar', None) or (slugify(getattr(property, 'title_ar', None) or property.title or ""))
        },
        
        # Location
        "location": {
            "country_id": getattr(property, 'country_id', None) or 1,
            "country": "Jordan",
            "city_id": property.city_id,
            "city": property.city.name if property.city else None,
            "region_id": property.location_id,
            "region": property.area_rel.name if property.area_rel else None,
            "address": {
                "en": property.location_name or (f"{property.area_rel.name} - {property.city.name}" if property.area_rel and property.city else None),
                "ar": getattr(property, 'address_ar', None) or property.location_name or None
            },
            "latitude": float(property.latitude) if property.latitude else None,
            "longitude": float(property.longitude) if property.longitude else None,
            "map_embed_url": f"https://maps.google.com/?q={property.latitude},{property.longitude}" if property.latitude and property.longitude else None
        },
        
        # General
        "general": {
            "floor_type": getattr(property, 'floor_type', None),
            "floor_number": getattr(property, 'floor_number', None),
            "building_status": getattr(property, 'building_status', None),
            "built_in_year": getattr(property, 'built_in_year', None),
            "furniture_status": property.furniture_status,
            "furniture_condition": getattr(property, 'furniture_condition', None),
            "garage_type": getattr(property, 'garage_type', None),
            "total_floors_in_building": getattr(property, 'total_floors_in_building', None)
        },
        
        # Details
        "details": {
            "built_up_area": float(property.area) if property.area else None,
            "land_area": float(property.plot_area) if property.plot_area else None,
            "garden_area": float(getattr(property, 'garden_area', None)) if getattr(property, 'garden_area', None) else None,
            "area_unit": getattr(property, 'area_unit', 'sqm'),
            "bedrooms": property.bedrooms,
            "master_bedrooms": getattr(property, 'master_bedrooms', None),
            "bathrooms": property.bathrooms,
            "living_rooms": getattr(property, 'living_rooms', None),
            "salons": getattr(property, 'salons', None),
            "balconies": getattr(property, 'balconies', None),
            "entrances": getattr(property, 'entrances', None),
            "kitchens": getattr(property, 'kitchens', None) or property.rooms,
            "kitchen_type": getattr(property, 'kitchen_type', None),
            "maid_rooms": getattr(property, 'maid_rooms', None) or maid_rooms,
            "driver_rooms": getattr(property, 'driver_rooms', None) or driver_rooms,
            "store_rooms": getattr(property, 'store_rooms', None) or store_rooms
        },
        
        # Features
        "features": {
            "amenities": amenities,
            "finishing": more_features.get("Finishing", "").lower() if more_features else None,
            "windows": more_features.get("Windows", "").lower().replace(" ", "_") if more_features else None,
            "window_shutters": more_features.get("Window Shutters", "").lower() if more_features else None,
            "doors": more_features.get("Doors", "").lower() if more_features else None,
            "air_conditioning": more_features.get("Air Conditioning", "").lower().replace(" ", "_") if more_features else None,
            "heating_system": more_features.get("Heating System", "").lower().replace(" ", "_") if more_features else None,
            "heating_fuel": more_features.get("Heating Fuel", "").lower() if more_features else None,
            "has_view": getattr(property, 'has_view', False),
            "view_type": getattr(property, 'view_type', None) or []
        },
        
        # Pricing
        "pricing": {
            "listing_type": determine_listing_type(property),
            "annual_rent": annual_rent,
            "monthly_rent": float(getattr(property, 'monthly_rent', None)) if getattr(property, 'monthly_rent', None) else monthly_rent,
            "quarterly_rent": float(getattr(property, 'quarterly_rent', None)) if getattr(property, 'quarterly_rent', None) else quarterly_rent,
            "selling_price": float(property.selling_price_amount) if property.selling_price_amount else None,
            "currency": property.rent_price_currency or property.selling_price_currency or "JOD",
            "price_on_request": getattr(property, 'price_on_request', False),
            "rent_commission_percent": float(getattr(property, 'rent_commission_percent', None)) if getattr(property, 'rent_commission_percent', None) else None,
            "contract_duration": getattr(property, 'contract_duration', None),
            "contract_duration_unit": getattr(property, 'contract_duration_unit', None),
            "payment_method": getattr(property, 'payment_method', None),
            "is_negotiable": getattr(property, 'is_negotiable', False),
            "down_payment": float(getattr(property, 'down_payment', None)) if getattr(property, 'down_payment', None) else None,
            "installment_available": getattr(property, 'installment_available', False),
            "installment_details": getattr(property, 'installment_details', None)
        },
        
        # Media
        "media": {
            "thumbnail": images_list[0] if images_list else None,
            "images": [
                {
                    "id": idx + 1,
                    "url": img_url,
                    "thumb_url": img_url,  # Or generate thumb URL
                    "is_primary": idx == 0,
                    "order": idx + 1,
                    "caption": None
                }
                for idx, img_url in enumerate(images_list)
            ],
            "videos": [],
            "virtual_tour_url": getattr(property, 'virtual_tour_url', None),
            "floor_plan_images": [],
            "documents": []
        },
        
        # Agent (if available)
        "agent": {
            "id": property.agent.id,
            "name": property.agent.name,
            "phone": property.agent.phone,
            "whatsapp": property.agent.whatsapp,
            "email": property.agent.email,
            "photo": property.agent.photo,
            "license_number": property.agent.license_number
        } if hasattr(property, 'agent') and property.agent else None,
        
        # Owner (if available)
        "owner": {
            "id": property.owner.id,
            "name": property.owner.name,
            "phone": property.owner.phone,
            "email": property.owner.email,
            "is_private": property.owner.is_private
        } if hasattr(property, 'owner') and property.owner else None,
        
        # Created by (if available)
        "created_by": {
            "id": property.created_by.id,
            "name": property.created_by.name,
            "role": property.created_by.role
        } if hasattr(property, 'created_by') and property.created_by else None,
        
        # Timestamps
        "created_at": property.created_at.isoformat() if property.created_at else None,
        "updated_at": property.updated_at.isoformat() if property.updated_at else None,
        "published_at": (getattr(property, 'published_at', None) or property.created_at).isoformat() if (getattr(property, 'published_at', None) or property.created_at) else None,
        "expires_at": getattr(property, 'expires_at', None).isoformat() if getattr(property, 'expires_at', None) else None,
        "sold_at": getattr(property, 'sold_at', None).isoformat() if getattr(property, 'sold_at', None) else None,
        "rented_at": getattr(property, 'rented_at', None).isoformat() if getattr(property, 'rented_at', None) else None
    }
    
    return result
```

---

## Migration Strategy

### Phase 1: Basic Structure (Low Effort, High Impact)
**Timeline:** 2-3 days  
**Priority:** High

1. **Restructure existing data** into nested format
2. **Generate reference_number** from existing ID
3. **Map existing fields** to new structure
4. **Extract data from `more_features`** JSON to structured fields
5. **Transform images** array to media objects

**Impact:** Immediate structure improvement, no database changes needed initially

### Phase 2: Multi-Language Support (Medium Effort, High Impact)
**Timeline:** 1-2 weeks  
**Priority:** High

1. **Create translation tables**
2. **Migrate existing English data** to translations
3. **Add Arabic translation support** (translation API or manual)
4. **Update API to accept language parameter**
5. **Generate slugs** for both languages

**Impact:** Enables i18n, critical for market expansion

### Phase 3: Enhanced Details (Medium Effort, Medium Impact)
**Timeline:** 1 week  
**Priority:** Medium

1. **Add new database columns** for general/details
2. **Create migration scripts** to populate from CSV
3. **Update import scripts** to capture new fields
4. **Update API schemas**

**Impact:** Better data granularity, improved search/filter capabilities

### Phase 4: Media Management (High Effort, Medium Impact)
**Timeline:** 2-3 weeks  
**Priority:** Medium

1. **Create media tables** (images, videos, documents)
2. **Migrate existing images** to new structure
3. **Implement thumbnail generation**
4. **Add image ordering and metadata**

**Impact:** Better media organization, improved performance

### Phase 5: Agent/Owner System (High Effort, High Impact)
**Timeline:** 2-3 weeks  
**Priority:** High

1. **Create agent and owner tables**
2. **Build agent/owner management APIs**
3. **Link properties to agents/owners**
4. **Add authentication/authorization**

**Impact:** Core business feature, enables property management

### Phase 6: Advanced Features (Low Priority)
**Timeline:** 1-2 weeks  
**Priority:** Low

1. **Virtual tours**
2. **Document management**
3. **Advanced pricing options**
4. **Contract management**

**Impact:** Nice to have features

---

## Effectiveness & Recommendations

### Benefits

1. **Better Structure**
   - Nested objects improve readability
   - Logical grouping of related fields
   - Easier to extend in future

2. **Multi-Language Support**
   - Enables Arabic market
   - SEO-friendly slugs
   - Better user experience

3. **Rich Metadata**
   - Agent/Owner tracking
   - Publication lifecycle
   - Better search/filter capabilities

4. **Media Management**
   - Proper image ordering
   - Thumbnail support
   - Video/document support

5. **API Consistency**
   - Standardized response format
   - Easier frontend integration
   - Better documentation

### Challenges

1. **Data Migration**
   - Existing data needs transformation
   - Some fields may be empty initially
   - Requires careful mapping

2. **Backward Compatibility**
   - Old API clients may break
   - Need versioning strategy
   - Gradual migration path

3. **Performance**
   - More joins required
   - Larger response payloads
   - Need caching strategy

4. **Development Time**
   - Significant schema changes
   - Multiple migration phases
   - Testing overhead

5. **Data Completeness**
   - Many new fields will be NULL initially
   - Requires data collection/enhancement
   - May need manual data entry

### Recommendation

**Recommended Approach: Incremental Migration**

1. **Start with Phase 1** - Restructure existing data (quick win)
2. **Add multi-language** - Critical for market expansion
3. **Enhance details gradually** - As data becomes available
4. **Build agent/owner system** - Core business requirement
5. **Add media management** - When needed

**Timeline:** 6-8 weeks for full implementation  
**Risk Level:** Medium (manageable with proper planning)  
**ROI:** High (better API, multi-language, better UX)

### Compatibility Strategy

**Option A:** Create new endpoint `/api/v2/properties` with new format, keep old endpoints  
**Option B:** Add query parameter `format=v2` to existing endpoints  
**Option C:** Version the API with `/api/v1/properties` (old) and `/api/v2/properties` (new)

**Recommended:** Option C (API versioning) for clean separation and gradual migration.

---

## Conclusion

The new format is **significantly more comprehensive** and provides:
- Better structure and organization
- Multi-language support
- Rich metadata and relationships
- Better media management
- Agent/Owner tracking

**Data Availability Summary:**
- **~70% of fields** can be extracted directly or derived from existing CSV
- **~20% of fields** require translation or external data (Arabic translations)
- **~10% of fields** are completely missing and need manual input or defaults

**Next Steps:**
1. Review and approve this transformation plan
2. Decide on compatibility strategy (new endpoint vs versioning)
3. Create database migration for new columns
4. Implement transformation function in schema layer
5. Update import script to populate new fields from CSV
6. Test transformation with sample properties
7. Deploy and monitor for any issues

---

**Document Version:** 2.0  
**Last Updated:** 2024-01-XX  
**Status:** Ready for Implementation

