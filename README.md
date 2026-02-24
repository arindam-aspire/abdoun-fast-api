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
│       └── geocoding.py        # Geocoding service
├── alembic/                    # Database migrations
│   ├── versions/               # Migration files
│   └── env.py                  # Alembic environment
├── scripts/
│   ├── seed_reference_data.py  # Seed reference tables (categories, types, etc.)
│   ├── import_normalized_csv.py  # Import properties into normalized tables
│   ├── check_data_status.py   # Check data counts in all tables
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
   
   **Expected Output:**
   ```
   INFO  [alembic.runtime.migration] Running upgrade 0003_add_location_name -> 0004_normalized_tables
   INFO  [alembic.runtime.migration] Running upgrade 0004_normalized_tables -> 0005_drop_old_props
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
  - **Response:** Returns `PropertySearchResponse` with `data`, `page`, `pageSize`, and `total`

- **GET** `/api/v1/properties/{id}` - Get property details
  - Returns complete property information including all fields

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
# Imports properties from CSV into normalized tables
python scripts/import_normalized_csv.py
```

**Update More Features Column (for existing data):**
```powershell
# Updates only the more_features JSON column for existing properties
# Use this if you've already imported data and want to populate more_features
python scripts/update_more_features.py
```

**Check Data Status:**
```powershell
# Displays counts for all tables
python scripts/check_data_status.py
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
  - `title`, `description`, `selling_price_amount`, `rent_price_amount`, etc.
  - `images` (String) - JSON array of image URLs
  - `more_features` (JSONB) - JSON object with key-value pairs (e.g., `{"Finishing": "Deluxe", "Windows": "Double Glazed"}`)
  - `location` (Geometry POINT) - PostGIS geometry for spatial queries
  - `created_at`, `updated_at` - Timestamps

**Indexes:**
- Primary key on `id` (UUID)
- Unique index on `url`
- GIST index on `location` (for spatial queries)
- Foreign key indexes on all relationship columns

## Development

### Running Tests
```powershell
python scripts/test_endpoints.py
```

### Database Migrations

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

## License

[Your License Here]

## Contributing

[Contributing Guidelines Here]
