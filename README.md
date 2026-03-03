# Real Estate Map API

A production-ready FastAPI application for managing and searching real estate properties with spatial queries using PostgreSQL and PostGIS.

## Features

- 🗺️ **Spatial Search**: Search properties by geographic bounds or polygons
- 📍 **Geocoding**: Automatic geocoding with Nominatim, Google Search, and Azure OpenAI fallback
- 🏠 **Property Management**: Full CRUD operations for property listings
- 📊 **CSV Import**: Bulk import properties from CSV files
- 🔍 **Advanced Filtering**: Search by status, category, type, city, location, price range, and more
- 🔗 **Similar Properties**: Find similar properties based on category, location, price, bedrooms, bathrooms, and area
- 📄 **Pagination**: Page-based pagination with configurable page size
- 🌍 **Multi-Language (i18n)**: Property title and description in English, Arabic, Spanish, and French via `property_translations` table
- 🚀 **Fast & Scalable**: Built with FastAPI, SQLAlchemy 2.0, and PostGIS

## Tech Stack

- **Framework**: FastAPI 0.115.0
- **Database**: PostgreSQL with PostGIS extension
- **ORM**: SQLAlchemy 2.0.34
- **Spatial**: GeoAlchemy2 0.15.2
- **Validation**: Pydantic v2.9.2
- **Migrations**: Alembic 1.13.3
- **Data Processing**: Pandas 2.2.3

## Project Structure

```
abdoun_fast_api/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application entry point
│   ├── api/
│   │   └── v1/
│   │       ├── router.py       # API router aggregation
│   │       └── routes/
│   │           ├── properties.py  # Property CRUD endpoints
│   │           └── search.py      # Spatial search endpoints
│   ├── core/
│   │   └── config.py           # Application settings
│   ├── db/
│   │   ├── base.py             # SQLAlchemy Base
│   │   └── session.py          # Database session management
│   ├── models/
│   │   └── property.py         # Property database model
│   ├── schemas/
│   │   └── property.py         # Pydantic schemas for API
│   └── services/
│       ├── csv_importer.py      # CSV import logic
│       ├── normalized_importer.py  # Normalized CSV import (writes property_translations en)
│       ├── translation_service.py  # i18n: translate_text, get_title_description_all_languages
│       └── geocoding.py        # Geocoding service
├── alembic/                    # Database migrations
│   ├── versions/               # Migration files
│   └── env.py                  # Alembic environment
├── scripts/
│   ├── seed_reference_data.py  # Seed reference tables (categories, types, etc.)
│   ├── import_normalized_csv.py  # Import properties into normalized tables
│   ├── backfill_property_translations.py  # Backfill en + optional ar, esp, fr translations
│   ├── backfill_reference_number.py      # Backfill reference_number from CSV property_id
│   ├── backfill_feature_values_from_csv.py  # Backfill PropertyFeature.value from CSV more_features
│   ├── backfill_meta_features_from_csv.py   # Backfill Floor Type, Floor, Garage, Terrace Area, etc. from CSV as features
│   ├── check_data_status.py   # Check data counts (includes property_translations by language)
│   ├── test_endpoints.py       # API endpoint tests
│   └── enrich_csv_with_coordinates.py  # Geocode CSV locations
├── data/
│   └── abdoun_merged_properties.csv  # Sample data
├── docker-compose.yml          # Docker setup
├── Dockerfile                  # Application container
├── requirements.txt            # Python dependencies
├── alembic.ini                 # Alembic configuration
└── README.md                   # This file
```

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 12+ with PostGIS extension (installed locally on your machine)
- Docker and Docker Compose (optional, for containerized API - uses your local database)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd abdoun_fast_api
   ```

2. **Create virtual environment**
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```powershell
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   Create a `.env` file:
   ```env
   # Database Configuration
   # Use localhost for local development - it will auto-convert to host.docker.internal in Docker
   DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/realestate
   
   # Application Configuration
   ENVIRONMENT=local
   DEBUG=true
   
   # Optional: Azure OpenAI for geocoding fallback
   AZURE_OPENAI_KEY=your_key_here
   AZURE_ENDPOINT=your_endpoint_here
   AZURE_API_VERSION=2023-05-15
   AZURE_DEPLOYMENT_NAME=your_deployment_name
   ```
   
   **Note:** The `DATABASE_URL` uses `localhost` which works for both:
   - **Local development**: Connects directly to `localhost:5432`
   - **Docker**: Automatically converts `localhost` to `host.docker.internal` to access your local database

5. **Set up database**
   
   **Step 5.1: Create Database and Enable PostGIS**
   ```powershell
   # Create database (replace 'Abdoun_RE' with your database name)
   psql -U postgres -c "CREATE DATABASE Abdoun_RE;"
   psql -U postgres -d Abdoun_RE -c "CREATE EXTENSION postgis;"
   ```
   
   **Step 5.2: Update .env with correct database name**
   ```env
   DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/Abdoun_RE
   ```
   
   **Step 5.3: Run database migrations**
   ```powershell
   # This creates all normalized tables and drops old properties table
   python -m alembic upgrade head
   ```
   
   **Step 5.4: Populate new columns after migrations (currency, rent_commission_percent, contract_duration, payment_method)**  
   If you added migrations 0010 (currency) or 0011 (rent_commission, contract_duration, payment_method), run the normalized import so these fields are filled from the CSV. New imports get them automatically; for an existing DB, re-run the import (existing rows are skipped by URL; only new rows get the new fields unless you run a backfill).
   ```powershell
   python scripts/import_normalized_csv.py
   # Or with custom CSV path:
   python scripts/import_normalized_csv.py --csv-path data/abdoun_merged_properties.csv
   ```
   
   **Expected migration output (example):**
   ```
   INFO  [alembic.runtime.migration] Running upgrade 0010_currency -> 0011_pricing_extras, add rent_commission_percent, contract_duration, payment_method to properties_normalized
   ```

6. **Seed reference data**
   
   **Step 6.1: Seed categories, types, cities, areas, statuses, and features**
   ```powershell
   python scripts/seed_reference_data.py
   ```
   
   **Expected Output:**
   ```
   ✓ Created category: Residential
   ✓ Created property type: Apartment
   ✓ Created city: Amman
   ✓ Created area: Abdoun
   ✓ Created status: Verified
   ✓ Created feature: Elevator
   ✓ Linked feature 'Elevator' to category 'Residential'
   ...
   ```

7. **Import property data from CSV**
   
   **Step 7.1: Import properties into normalized tables**
   ```powershell
   python scripts/import_normalized_csv.py
   ```
   
   **Expected Output:**
   ```
   Reading CSV file: data/abdoun_merged_properties.csv
   Imported 2358 properties, skipped 0 duplicates
   ```
   
   **Note:** The import script automatically:
   - Parses `more_features` from CSV (pipe-separated format)
   - Converts it to key-value JSON pairs (e.g., `{"Finishing": "Deluxe", "Windows": "Double Glazed"}`)
   - Stores it in the `more_features` JSON column
   
   **Step 7.2: Verify data import** (optional)
   ```powershell
   # Check data status
   python scripts/check_data_status.py
   ```
   
   **Step 7.3: Backfill multi-language translations** (optional)
   ```powershell
   # Add English rows to property_translations from existing title/description
   python scripts/backfill_property_translations.py
   # Optionally add Arabic, Spanish, French (requires: pip install deep-translator)
   python scripts/backfill_property_translations.py --translate-other-languages --workers 10 --batch 50
   # Verify: python scripts/backfill_property_translations.py --status
   ```
   
   **Step 7.4: Backfill reference_number** (if you had existing data before migration 0008)
   ```powershell
   python scripts/backfill_reference_number.py
   ```
   
   Or use SQL:
   ```sql
   SELECT COUNT(*) FROM properties_normalized;
   -- Expected: 2358
   
   -- Check more_features JSON data
   SELECT id, title, more_features 
   FROM properties_normalized 
   WHERE more_features IS NOT NULL 
   LIMIT 5;
   ```

8. **Start the server**
   ```powershell
   uvicorn app.main:app --reload
   ```

9. **Test the API**
   
   **Step 9.1: Run automated tests**
   ```powershell
   python scripts/test_endpoints.py
   ```
   
   **Expected Output:**
   ```
   ✅ PASS: List Properties
   ✅ PASS: Get Property Detail
   ✅ PASS: Search with Filters
   ✅ PASS: Search by Bounds
   ✅ PASS: Search by Polygon
   
   Total: 5/5 tests passed
   ```
   
   **Step 9.2: Manual testing**
   - API: http://127.0.0.1:8000
   - Interactive Docs: http://127.0.0.1:8000/docs
   - ReDoc: http://127.0.0.1:8000/redoc
   
   **Test endpoints:**
   ```powershell
   # List properties
   GET http://127.0.0.1:8000/api/v1/properties?page=1&pageSize=12
   
   # Get property detail (use ID from list response)
   GET http://127.0.0.1:8000/api/v1/properties/{id}
   
   # Get similar properties
   GET http://127.0.0.1:8000/api/v1/properties/{id}/similar?limit=20
   
   # Search with filters
   GET http://127.0.0.1:8000/api/v1/properties?status=buy&category=residential&city=amman&page=1&pageSize=12
   ```

## Docker Setup

**Note:** Docker setup uses your **local PostgreSQL database** (not a Docker database container). Make sure your local PostgreSQL server is running before starting Docker.

1. **Ensure local database is set up**
   ```powershell
   # Create database and enable PostGIS (if not already done)
   psql -U postgres -c "CREATE DATABASE realestate;"
   psql -U postgres -d realestate -c "CREATE EXTENSION postgis;"
   ```

2. **Start the API container**
   ```powershell
   docker-compose up -d
   ```
   
   The container will automatically connect to your local database using `host.docker.internal`. Your `.env` file can use `localhost` - it will be automatically converted when running in Docker.

3. **Run migrations** (if needed)
   ```powershell
   docker-compose exec api python -m alembic upgrade head
   ```

4. **Seed reference data and import properties**
   ```powershell
   # Seed reference data (categories, types, cities, etc.)
   docker-compose exec api python scripts/seed_reference_data.py
   
   # Import property data
   docker-compose exec api python scripts/import_normalized_csv.py
   ```

5. **View logs**
   ```powershell
   docker-compose logs -f api
   ```

6. **Stop the container**
   ```powershell
   docker-compose down
   ```

**Important:** 
- The Docker setup **only runs the API container** - it does not create a database container
- Your `.env` file should have `DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/realestate`
- The application automatically converts `localhost` to `host.docker.internal` when running in Docker
- Make sure your local PostgreSQL server is running and accessible

## API Endpoints

### Properties

- **GET** `/api/v1/properties` - List properties with pagination and filtering
  - **Query Parameters:**
    - `page` (int, default: 1) - Page number
    - `pageSize` (int, default: 50) - Number of properties per page
    - `status` (string, optional) - Filter by status (e.g., "buy", "rent")
    - `category` (string, optional) - Filter by category (e.g., "residential", "commercial")
    - `type` (string, optional) - Filter by property type (e.g., "apartments", "villas")
    - `city` (string, optional) - Filter by city (e.g., "amman")
    - `locations` (string, optional) - Filter by location/area (e.g., "abdoun")
    - `budgetMin` / `minPrice` (float, optional) - Minimum price filter
    - `budgetMax` / `maxPrice` (float, optional) - Maximum price filter
    - `exclusive` (bool, optional) - Filter by exclusive status (`true` for exclusive only, `false` for non-exclusive only)
    - `lang` (string, optional) - Language code for display (`en`, `ar`, `esp`, `fr`); list/detail return **multi-language objects** for `title`/`description` (see [Multi-Language Support](#multi-language-i18n-support))
  - **Response:** Returns `PropertySearchResponse` with `data`, `page`, `pageSize`, and `total`. Each property has `title` and (on detail) `description` as objects: `{"en": "...", "ar": "...", "esp": "...", "fr": "..."}`

- **GET** `/api/v1/properties/{id}` - Get property details
  - Returns complete property information. `title` and `description` are multi-language objects: `{"en": "...", "ar": "...", "esp": "...", "fr": "..."}`. Optional query: `lang` (for future use; response always includes all languages)

- **GET** `/api/v1/properties/{id}/similar?limit=20` - Get similar properties
  - **Query Parameters:**
    - `limit` (int, default: 20, max: 50) - Maximum number of similar properties to return
  - **Response:** Returns `PropertySearchResponse` with similar properties
  - **Similarity Criteria:**
    The endpoint finds similar properties based on multiple criteria:
    - **Same Category/Type**: Matches properties with the same category (e.g., "Apartment", "Villa")
    - **Same City/Location**: Extracts city from location_name (e.g., "Abdoun - Amman" → "Amman") and matches properties in the same city
    - **Similar Price Range**: ±20% tolerance from the reference property's price
      - Uses selling price if available, otherwise uses rent price
      - Matches properties with prices within the tolerance range
    - **Similar Bedrooms**: ±1 bedroom difference (e.g., if reference has 3 bedrooms, matches 2, 3, or 4 bedrooms)
    - **Similar Bathrooms**: ±1 bathroom difference (e.g., if reference has 2 bathrooms, matches 1, 2, or 3 bathrooms)
    - **Similar Built-up Area**: ±20% tolerance from the reference property's area
    - **Excludes Current Property**: The reference property itself is excluded from results
  - **Example:**
    ```
    GET /api/v1/properties/59/similar?limit=20
    ```
    This will find up to 20 properties similar to property ID 59 based on the criteria above.

### Locations

- **GET** `/api/v1/cities` - Get list of all active cities
  - **Response:** Returns list of cities with `id` and `name`
  - **Example:**
    ```powershell
    GET http://localhost:8000/api/v1/cities
    ```

- **GET** `/api/v1/areas` - Get list of areas, optionally filtered by city
  - **Query Parameters:**
    - `city` (string, optional) - Filter areas by city name (case-insensitive)
  - **Response:** Returns list of areas with `id`, `name`, `city_id`, and `city_name`
  - **Examples:**
    ```powershell
    # Get all areas
    GET http://localhost:8000/api/v1/areas
    
    # Get areas in a specific city
    GET http://localhost:8000/api/v1/areas?city=amman
    ```

### Search

- **POST** `/api/v1/properties/geo-search` - Search properties by geographic bounds or polygon

**Request Body:**
```json
{
  "mode": "bounds",  // or "polygon"
  "bounds": {
    "min_lng": 35.8,
    "min_lat": 31.9,
    "max_lng": 36.0,
    "max_lat": 32.0
  },
  "limit": 100
}
```

### Import

- **POST** `/api/v1/import-csv` - Import properties from CSV file

**Query Parameters:**
- `geocode_missing` (bool, default: false) - Geocode locations without coordinates

**Note:** Property IDs in API responses are integer hashes derived from UUID primary keys for API compatibility. The system uses deterministic SHA256 hashing to ensure consistent IDs across server restarts.

## Geocoding

The application supports multiple geocoding services:

1. **Nominatim** (Primary) - Free, rate-limited to 1 req/sec
2. **Google Search** (Fallback) - Free, no API key needed
3. **Azure OpenAI** (Final Fallback) - Requires configuration

See [AZURE_OPENAI_GEOCODING.md](AZURE_OPENAI_GEOCODING.md) for Azure OpenAI setup.

## Scripts

### Database Setup Scripts

**Seed Reference Data:**
```powershell
# Seeds categories, types, cities, areas, statuses, features, and relationships
python scripts/seed_reference_data.py
```

**Import Property Data:**
```powershell
# Imports properties from CSV into normalized tables (includes currency, rent_commission_percent, contract_duration, payment_method from CSV)
python scripts/import_normalized_csv.py

# Custom CSV path
python scripts/import_normalized_csv.py --csv-path data/abdoun_merged_properties.csv
```
After running `alembic upgrade head` for migrations 0010/0011, run the import above to populate the new columns.

**Update More Features Column (for existing data):**
```powershell
# Updates only the more_features JSON column for existing properties
# Use this if you've already imported data and want to populate more_features
python scripts/update_more_features.py
```

**Check Data Status:**
```powershell
# Displays counts for all tables and property_translations by language (en, ar, esp, fr)
python scripts/check_data_status.py
```

**Backfill Property Translations (Multi-Language):**
```powershell
# 1) Backfill English only (from properties_normalized.title/description)
python scripts/backfill_property_translations.py

# 2) Show current translation counts (verify what's in DB)
python scripts/backfill_property_translations.py --status

# 3) Backfill ar, esp, fr by translating from en (uses deep_translator when available)
python scripts/backfill_property_translations.py --translate-other-languages

# 4) Faster run: more workers, smaller commit batches
python scripts/backfill_property_translations.py --translate-other-languages --workers 10 --batch 50

# 5) Dry run (no DB writes)
python scripts/backfill_property_translations.py --translate-other-languages --dry-run
```

**Backfill Reference Number (for existing data):**
```powershell
# After migration 0008_add_reference_number: fill reference_number from CSV property_id (match by url)
python scripts/backfill_reference_number.py

# Dry run (show what would be updated, no commit)
python scripts/backfill_reference_number.py --dry-run

# Custom CSV path
python scripts/backfill_reference_number.py --csv-path data/abdoun_merged_properties.csv
```

**Backfill Feature Values (for Finishing, Windows, etc. from CSV more_features):**
```powershell
# Populate PropertyFeature.value for selected keys (Finishing, Windows, Window Shutters, Doors,
# Air Conditioning, Heating System, Heating Fuel) using CSV more_features (matched by url)
python scripts/backfill_feature_values_from_csv.py

# Dry run (show what would be updated, no commit)
python scripts/backfill_feature_values_from_csv.py --dry-run

# Custom CSV path
python scripts/backfill_feature_values_from_csv.py --csv-path data/abdoun_merged_properties.csv
```

**Backfill Meta Features (Floor Type, Floor, Garage, Terrace Area, etc. from CSV):**
```powershell
# Populate Floor Type, Floor, Building Status, Garage, Terrace Area, Garden Area, Master Bedrooms, Kitchens, Furniture
# as Feature + PropertyFeature.value (so general/details in API can be filled from features)
python scripts/backfill_meta_features_from_csv.py

# Dry run
python scripts/backfill_meta_features_from_csv.py --dry-run

# Custom CSV path
python scripts/backfill_meta_features_from_csv.py --csv-path data/abdoun_merged_properties.csv
```

### Testing Scripts

**Test API Endpoints:**
```powershell
# Runs comprehensive API tests
python scripts/test_endpoints.py
```

**Enrich CSV with Coordinates:**
```powershell
# Geocodes locations in CSV file
python scripts/enrich_csv_with_coordinates.py data\abdoun_merged_properties.csv
```

## Database Schema

### Normalized Database Structure

The database uses a normalized structure with separate tables for:

**Reference Tables:**
- `property_categories` - Categories (Residential, Commercial, Land)
- `property_types` - Types (Apartment, Villa, Office, etc.)
- `cities` - Cities (Amman, Irbid, etc.)
- `areas` - Areas/Locations (Abdoun, Khalda, etc.)
- `property_status` - Status values (Verified, Pending, etc.)
- `features` - Property features (Elevator, Parking, etc.)
- `search_fields` - Searchable fields configuration

**Relationship Tables:**
- `category_features` - Links features to categories
- `type_features` - Links features to property types
- `category_search_fields` - Links search fields to categories
- `property_features` - Links features to properties (many-to-many)

**Main Table:**
- `properties_normalized` - Main property table with UUID primary key
  - `id` (UUID, PK) - UUID primary key (converted to int hash for API)
  - `category_id` (FK) - References `property_categories`
  - `type_id` (FK) - References `property_types`
  - `city_id` (FK) - References `cities`
  - `location_id` (FK) - References `areas`
  - `property_status_id` (FK) - References `property_status`
  - `url` (String, Unique) - Original property URL
  - `title`, `description` - Legacy single-language fields (fallback; prefer `property_translations`)
  - `selling_price_amount`, `rent_price_amount`, etc.
  - `images` (String) - JSON array of image URLs
  - `more_features` (JSONB) - JSON object with key-value pairs (e.g., `{"Finishing": "Deluxe", "Windows": "Double Glazed"}`)
  - `reference_number` (String, nullable) - Display reference from source (e.g. CSV property_id "01002")
  - `location` (Geometry POINT) - PostGIS geometry for spatial queries
  - `created_at`, `updated_at` - Timestamps

**Translations Table (i18n):**
- `property_translations` - Title and description per language (best practice: separate table, not JSONB)
  - `id` (SERIAL, PK)
  - `property_id` (UUID, FK → `properties_normalized.id` ON DELETE CASCADE)
  - `language_code` (VARCHAR(5)) - `en`, `ar`, `esp`, `fr`
  - `title` (TEXT)
  - `description` (TEXT)
  - `created_at`, `updated_at`
  - **UNIQUE(property_id, language_code)** - One row per property per language
  - Index on `(property_id, language_code)` for fast lookups
  - Slug is **not** stored here; derive from title when needed for SEO.

**Indexes:**
- Primary key on `id` (UUID)
- Unique index on `url`
- GIST index on `location` (for spatial queries)
- GIST index on `location` (for spatial queries)
- Foreign key indexes on all relationship columns
- Index on `property_translations(property_id, language_code)`

## Multi-Language (i18n) Support

### Overview

Property **title** and **description** are stored per language in the `property_translations` table. Supported languages: **en** (English), **ar** (Arabic), **esp** (Spanish), **fr** (French). Slug is not translated; derive from title when needed.

### Table Design

| Column          | Type        | Description |
|-----------------|-------------|-------------|
| `id`            | SERIAL (PK) | Primary key |
| `property_id`   | UUID (FK)   | References `properties_normalized.id` ON DELETE CASCADE |
| `language_code` | VARCHAR(5)  | `en`, `ar`, `esp`, `fr` |
| `title`         | TEXT        | Title in this language |
| `description`   | TEXT        | Description in this language |
| `created_at`    | TIMESTAMP   | |
| `updated_at`    | TIMESTAMP   | |

- **UNIQUE(property_id, language_code)** so each property has at most one row per language.
- Best practice: separate translation table (not JSONB) for indexing, filtering, and scaling.

### API Response Format

List and detail responses return **title** and **description** as objects keyed by language:

```json
{
  "id": 123,
  "title": {
    "en": "Apartment for Rent",
    "ar": "شقة للإيجار",
    "esp": "Apartamento en alquiler",
    "fr": "Appartement à louer"
  },
  "description": {
    "en": "Spacious furnished apartment in the heart of Dair Gbhar...",
    "ar": "شقة مفروشة واسعة في قلب دير غبار...",
    "esp": "...",
    "fr": "..."
  },
  ...
}
```

Frontend can pick the right key (`en`, `ar`, `esp`, `fr`) for the current locale.

### Translation Service

- **`translate_text(text, target_lang, source_lang)`** – Translates a string. Uses **deep_translator** (Google Translate, no API key) when installed; otherwise returns source text. Can be replaced with AWS Translate.
- **`get_or_create_translation(db, property_id, language_code, title=..., description=...)`** – Gets or creates a `property_translations` row.
- **`translate_property_to_language(db, property_id, target_lang, ...)`** – Translates a property’s title/description to one language and persists it.
- **`get_title_description_all_languages(prop)`** – Returns `(title_by_lang, description_by_lang)` dicts for API responses (keys: en, ar, esp, fr).

### Backfill Script

After migration `0007_add_property_translations` and importing properties:

1. **Backfill English** from existing `properties_normalized.title`/`description`:
   ```powershell
   python scripts/backfill_property_translations.py
   ```

2. **Check counts** (verify DB state):
   ```powershell
   python scripts/backfill_property_translations.py --status
   ```
   Example output:
   ```
   property_translations:
     total rows: 9432
     en: 2358
     ar: 2358
     esp: 2358
     fr: 2358
     (properties_normalized: 2358 properties)
   ```

3. **Backfill ar, esp, fr** by translating from en (parallel workers; requires `deep-translator` for real translation):
   ```powershell
   pip install deep-translator
   python scripts/backfill_property_translations.py --translate-other-languages
   ```
   Options: `--workers 8` (default), `--batch 100`, `--dry-run`.

### CSV Import

The normalized CSV importer writes **en** into `property_translations` when creating properties (from `property_name` and `description`). It also keeps `properties_normalized.title`/`description` for backward compatibility.

## Development

### Running Tests
```powershell
python scripts/test_endpoints.py
```

### Database Migrations

**After upgrading (e.g. `alembic upgrade head`):**  
To populate new columns (e.g. `currency`, `rent_commission_percent`, `contract_duration`, `payment_method`), run the normalized import so CSV data is loaded into the new fields:
```powershell
python scripts/import_normalized_csv.py
```

**Important:** Before running Alembic commands, ensure environment variables are loaded from `.env`:

```powershell
# Load environment variables (choose one method):
# Method 1: Dot-source the load script
. .\load_env.ps1

# Method 2: Use setup script to run commands directly
.\setup.ps1 -Command python -CommandArgs -m,alembic,upgrade,head
```

Create a new migration:
```powershell
# After loading env vars
python -m alembic revision --autogenerate -m "description"
```

Apply migrations:
```powershell
# After loading env vars
python -m alembic upgrade head
```

Rollback:
```powershell
# After loading env vars
python -m alembic downgrade -1
```

## PowerShell Setup Scripts

This project includes PowerShell scripts to help with environment setup on Windows:

### `setup.ps1` - Complete Setup Script
Comprehensive setup script that loads `.env` file and optionally runs commands:
```powershell
# Just load environment and show info
.\setup.ps1

# Load environment and run a command
.\setup.ps1 -Command python -CommandArgs -m,alembic,upgrade,head
.\setup.ps1 -Command alembic -CommandArgs upgrade,head
```

### `load_env.ps1` - Simple Environment Loader
Simple script to load `.env` into current PowerShell session:
```powershell
# Dot-source to load into current session
. .\load_env.ps1

# Now you can run commands normally
python -m alembic upgrade head
```

**Note:** PowerShell doesn't automatically load `.env` files. You must use one of these scripts or manually set `$env:DATABASE_URL` before running Alembic or other commands that need environment variables.

## Environment Variables

| Variable | Description | Default (Local) | Default (Docker) |
|----------|-------------|-----------------|------------------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+psycopg2://postgres:postgres@localhost:5432/realestate` | Auto-converts `localhost` to `host.docker.internal` |
| `ENVIRONMENT` | Environment name | `local` | `local` |
| `DEBUG` | Enable debug mode | `false` | `false` |
| `AZURE_OPENAI_KEY` | Azure OpenAI API key | - | - |
| `AZURE_ENDPOINT` | Azure OpenAI endpoint | - | - |
| `AZURE_API_VERSION` | Azure OpenAI API version | `2023-05-15` | `2023-05-15` |
| `AZURE_DEPLOYMENT_NAME` | Azure OpenAI deployment name | - | - |

**Note:** When running in Docker, the application automatically detects Docker environment and converts `localhost` in `DATABASE_URL` to `host.docker.internal` to access your local database. You can use `localhost` in your `.env` file for both local and Docker development.

## Exclusive Properties

### Overview

Exclusive properties are premium, high-value listings that represent approximately 5-6% of total properties. They are automatically identified based on specific criteria.

### Criteria for Exclusive Properties

A property is marked as **Exclusive** if **ALL 3 conditions** are met:

1. **High Price**:
   - Selling price > **800,000 JOD** OR
   - Rent price > **45,000 JOD**

2. **Premium Location**:
   - Located in: **Abdoun**, **Dabouq**, **Dair Gbhar**, **Al Rabieh**, **Al Sweifieh**

3. **Premium Type**:
   - Property type: **Villa** (includes Detached/Semi-Detached from CSV)

### Exclusive Property Statistics & Ranges

Based on current data (2,358 total properties):

- **Total Exclusive Properties**: 123 (5.2%)
- **Price Ranges**:
  - **Selling Price**: 1,000 - 950,000 JOD
  - **Rent Price**: 25,000 - 350,000 JOD
- **Distribution by Location**:
  - Abdoun: ~86 properties
  - Dabouq: ~43 properties
  - Dair Gbhar: ~6 properties
  - Al Rabieh: ~3 properties
  - Al Sweifieh: ~2 properties
- **Distribution by Type**:
  - Detached: ~111 properties
  - Semi-Detached: ~27 properties

### Using Exclusive Properties

**Filter in Regular List Endpoint:**
```powershell
# Get only exclusive properties
GET http://localhost:8000/api/v1/properties?exclusive=true&page=1&pageSize=12

# Get only non-exclusive properties
GET http://localhost:8000/api/v1/properties?exclusive=false&page=1&pageSize=12

# Combine with other filters
GET http://localhost:8000/api/v1/properties?exclusive=true&city=amman&status=buy&page=1&pageSize=12
```

**Dedicated Exclusive Endpoint:**
```powershell
# Get exclusive properties only
GET http://localhost:8000/api/v1/properties/exclusive?page=1&pageSize=12

# With all available filters
GET http://localhost:8000/api/v1/properties/exclusive?status=buy&category=residential&type=villas&city=amman&locations=abdoun&budgetMin=800000&budgetMax=2000000&page=1&pageSize=12

# Available query parameters (same as regular properties endpoint):
# - status: "buy" or "rent"
# - category: "residential", "commercial", "land" (or "lands")
# - type: property type slug (e.g., "apartments", "villas", "residential-lands")
# - city: city name, lowercase (e.g., "amman")
# - locations: comma-separated area/neighborhood names, lowercase (e.g., "abdoun,dabouq")
# - budgetMin / minPrice: minimum price in JD (numeric string)
# - budgetMax / maxPrice: maximum price in JD (numeric string)
# - page: page number (default: 1)
# - pageSize: items per page (default: 12, max: 100)
```

### Updating Exclusive Properties

To update the `is_exclusive` field for all properties:

```powershell
# Test first (dry run)
python scripts/update_exclusive_properties.py --dry-run

# Actually update database
python scripts/update_exclusive_properties.py
```

The script analyzes all properties and marks them as exclusive based on the approved criteria. It can be run multiple times safely.

## License

[Your License Here]

## Contributing

[Contributing Guidelines Here]
