# Real Estate Map API

A production-ready FastAPI application for managing and searching real estate properties with spatial queries using PostgreSQL and PostGIS.

## Features

- 🗺️ **Spatial Search**: Search properties by geographic bounds or polygons
- 📍 **Geocoding**: Automatic geocoding with Nominatim, Google Search, and Azure OpenAI fallback
- 🏠 **Property Management**: Full CRUD operations for property listings
- 📊 **CSV Import**: Bulk import properties from CSV files
- 🔍 **Advanced Filtering**: Search by status, category, type, city, locations, and price range
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
│   ├── import_from_csv.py      # CLI script for CSV import
│   ├── enrich_csv_with_coordinates.py  # Geocode CSV locations
│   └── test_endpoints.py       # API endpoint tests
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
   ```powershell
   # Create database and enable PostGIS
   psql -U postgres -c "CREATE DATABASE realestate;"
   psql -U postgres -d realestate -c "CREATE EXTENSION postgis;"
   
   # Load environment variables and run migrations
   # Option 1: Use setup script (recommended)
   .\setup.ps1 -Command python -CommandArgs -m,alembic,upgrade,head
   
   # Option 2: Load env and run manually
   . .\load_env.ps1
   python -m alembic upgrade head
   
   # Option 3: Direct command (if .env is already loaded)
   python -m alembic upgrade head
   ```

6. **Import sample data** (optional)
   ```powershell
   python scripts/import_from_csv.py data\abdoun_merged_properties.csv
   ```

7. **Start the server**
   ```powershell
   uvicorn app.main:app --reload
   ```

8. **Access the API**
   - API: http://127.0.0.1:8000
   - Interactive Docs: http://127.0.0.1:8000/docs
   - ReDoc: http://127.0.0.1:8000/redoc

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

4. **Import data** (optional)
   ```powershell
   docker-compose exec api python scripts/import_from_csv.py data/abdoun_merged_properties.csv
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

#### List Properties (with filters and pagination)
- **GET** `/api/v1/properties` - Search and list properties with optional filters

**Query Parameters:**
- `page` (int, default: 1) - Page number (1-based)
- `pageSize` (int, default: 12, max: 100) - Number of items per page
- `status` (string, optional) - Filter by listing type: `buy` or `rent`
- `category` (string, optional) - Filter by category: `residential`, `commercial`, `land` (or `lands`)
- `type` (string, optional) - Filter by property type slug (e.g., `apartments`, `villas`, `residential-lands`)
- `city` (string, optional) - Filter by city name (lowercase)
- `locations` (string, optional) - Filter by comma-separated area/neighborhood names (lowercase)
- `budgetMin` / `minPrice` (string, optional) - Minimum price in JD (numeric string)
- `budgetMax` / `maxPrice` (string, optional) - Maximum price in JD (numeric string)

**Response Format:**
```json
{
  "data": [...],
  "total": 100,
  "page": 1,
  "pageSize": 12
}
```

**Example Requests:**
```bash
# List all properties (first page)
GET /api/v1/properties

# Filter by status and pagination
GET /api/v1/properties?status=buy&page=1&pageSize=20

# Filter by category and type
GET /api/v1/properties?category=residential&type=apartments

# Filter by city and price range
GET /api/v1/properties?city=amman&budgetMin=100000&budgetMax=500000

# Combined filters
GET /api/v1/properties?status=buy&category=residential&type=apartments&city=amman&budgetMin=100000&budgetMax=500000&page=1&pageSize=12
```

#### Get Property Details
- **GET** `/api/v1/properties/{id}` - Get detailed information about a specific property

### Search (Spatial)

- **POST** `/api/v1/search` - Search properties by geographic bounds or polygon

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

See [TESTING_GUIDE.md](TESTING_GUIDE.md) for detailed API documentation and examples.

## Geocoding

The application supports multiple geocoding services:

1. **Nominatim** (Primary) - Free, rate-limited to 1 req/sec
2. **Google Search** (Fallback) - Free, no API key needed
3. **Azure OpenAI** (Final Fallback) - Requires configuration

See [AZURE_OPENAI_GEOCODING.md](AZURE_OPENAI_GEOCODING.md) for Azure OpenAI setup.

## Scripts

### Import CSV
```powershell
python scripts/import_from_csv.py data\abdoun_merged_properties.csv
```

### Import with geocoding
```powershell
python scripts/import_from_csv.py data\abdoun_merged_properties.csv --geocode-missing
```

### Update existing properties
```powershell
python scripts/import_from_csv.py data\abdoun_merged_properties.csv --update-coordinates
```

### Enrich CSV with coordinates
```powershell
python scripts/enrich_csv_with_coordinates.py data\abdoun_merged_properties.csv
```

### Test endpoints
```powershell
python scripts/test_endpoints.py
```

## Database Schema

### Properties Table

- `id` (Integer, PK) - Auto-incrementing primary key
- `url` (String, Unique) - Original property URL
- `title` (String) - Property title
- `description` (String) - Property description
- `category` (String) - Property category
- `status` (String) - Property status
- `selling_price_amount` (Numeric) - Selling price
- `selling_price_currency` (String) - Currency code
- `rent_price_amount` (Numeric) - Rental price
- `rent_price_currency` (String) - Currency code
- `bedrooms` (Integer) - Number of bedrooms
- `bathrooms` (Integer) - Number of bathrooms
- `built_up_area` (Numeric) - Area in square meters
- `features` (JSONB) - Array of features
- `more_features` (JSONB) - Additional features
- `images` (JSONB) - Array of image URLs
- `latitude` (Float) - Latitude coordinate
- `longitude` (Float) - Longitude coordinate
- `location_name` (String) - Human-readable location (e.g., "Dabouq - Amman")
- `location` (Geometry POINT) - PostGIS geometry for spatial queries
- `created_at` (Timestamp) - Creation timestamp
- `updated_at` (Timestamp) - Last update timestamp

**Indexes:**
- Primary key on `id`
- Unique index on `url`
- GIST index on `location` (for spatial queries)
- Index on `location_name` (for text search)

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
