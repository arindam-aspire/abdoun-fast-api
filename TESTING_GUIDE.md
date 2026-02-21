# API Testing Guide

This guide provides instructions for testing all endpoints of the Real Estate Map API.

## Prerequisites

1. **Start the FastAPI server:**
   ```powershell
   uvicorn app.main:app --reload
   ```
   The API will be available at: `http://127.0.0.1:8000`

2. **Access Interactive API Documentation:**
   - Swagger UI: http://127.0.0.1:8000/docs
   - ReDoc: http://127.0.0.1:8000/redoc

## Available Endpoints

### 1. List Properties
**GET** `/api/v1/properties`

List all properties with pagination.

**Query Parameters:**
- `limit` (int, default: 50): Number of properties to return
- `offset` (int, default: 0): Number of properties to skip

**Example Requests:**

```powershell
# Using curl
curl http://127.0.0.1:8000/api/v1/properties

# With pagination
curl "http://127.0.0.1:8000/api/v1/properties?limit=10&offset=0"

# Using PowerShell Invoke-WebRequest
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/properties?limit=5" | Select-Object -ExpandProperty Content
```

**Expected Response:**
```json
{
  "items": [
    {
      "id": 1,
      "url": "https://www.abdoun.com.jo/en/properties/view/1002",
      "title": "Apartment for Sale / Rent",
      "price": 320000.0,
      "price_currency": "JOD",
      "bedrooms": 3,
      "bathrooms": 4,
      "thumbnail": "https://...",
      "lat": 31.9880592,
      "lng": 35.8113021
    }
  ],
  "total": 50
}
```

---

### 2. Get Property Detail
**GET** `/api/v1/properties/{property_id}`

Get detailed information about a specific property.

**Path Parameters:**
- `property_id` (int): The property ID

**Example Requests:**

```powershell
# Using curl
curl http://127.0.0.1:8000/api/v1/properties/1

# Using PowerShell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/properties/1" | Select-Object -ExpandProperty Content
```

**Expected Response:**
```json
{
  "id": 1,
  "url": "https://www.abdoun.com.jo/en/properties/view/1002",
  "title": "Apartment for Sale / Rent",
  "description": "Type",
  "category": "Apartment for Sale / Rent",
  "status": "ok",
  "selling_price_amount": 320000.0,
  "selling_price_currency": "JOD",
  "rent_price_amount": 30000.0,
  "rent_price_currency": "JOD",
  "bedrooms": 3,
  "bathrooms": 4,
  "built_up_area": 400.0,
  "features": ["Maid's Room", "Laundry Room", ...],
  "more_features": ["Finishing", "Deluxe", ...],
  "images": ["https://...", ...],
  "latitude": 31.9880592,
  "longitude": 35.8113021,
  "location_name": "Dabouq - Amman"
}
```

---

### 3. Search Properties (Bounds)
**POST** `/api/v1/search`

Search properties within a geographic bounding box.

**Request Body:**
```json
{
  "mode": "bounds",
  "bounds": {
    "min_lng": 35.8,
    "min_lat": 31.9,
    "max_lng": 35.95,
    "max_lat": 32.0
  },
  "limit": 50
}
```

**Example Requests:**

```powershell
# Using curl
curl -X POST http://127.0.0.1:8000/api/v1/search `
  -H "Content-Type: application/json" `
  -d '{
    "mode": "bounds",
    "bounds": {
      "min_lng": 35.8,
      "min_lat": 31.9,
      "max_lng": 35.95,
      "max_lat": 32.0
    },
    "limit": 10
  }'

# Using PowerShell
$body = @{
    mode = "bounds"
    bounds = @{
        min_lng = 35.8
        min_lat = 31.9
        max_lng = 35.95
        max_lat = 32.0
    }
    limit = 10
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/search" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body | Select-Object -ExpandProperty Content
```

**Expected Response:**
```json
{
  "items": [
    {
      "id": 1,
      "title": "Apartment for Sale / Rent",
      "price": 320000.0,
      "lat": 31.9880592,
      "lng": 35.8113021,
      ...
    }
  ],
  "total": 10
}
```

---

### 4. Search Properties (Polygon)
**POST** `/api/v1/search`

Search properties within a GeoJSON polygon.

**Request Body:**
```json
{
  "mode": "polygon",
  "polygon": {
    "geojson": {
      "type": "Polygon",
      "coordinates": [[
        [35.85, 31.92],
        [35.95, 31.92],
        [35.95, 32.0],
        [35.85, 32.0],
        [35.85, 31.92]
      ]]
    }
  },
  "limit": 50
}
```

**Example Requests:**

```powershell
# Using curl
curl -X POST http://127.0.0.1:8000/api/v1/search `
  -H "Content-Type: application/json" `
  -d '{
    "mode": "polygon",
    "polygon": {
      "geojson": {
        "type": "Polygon",
        "coordinates": [[
          [35.85, 31.92],
          [35.95, 31.92],
          [35.95, 32.0],
          [35.85, 32.0],
          [35.85, 31.92]
        ]]
      }
    },
    "limit": 10
  }'
```

---

### 5. Import CSV
**POST** `/api/v1/import-csv`

Import properties from a CSV file.

**Query Parameters:**
- `geocode_missing` (bool, default: false): If true, geocode locations without coordinates

**Example Requests:**

```powershell
# Using curl
curl -X POST "http://127.0.0.1:8000/api/v1/import-csv?geocode_missing=false" `
  -F "file=@data/abdoun_merged_properties.csv"

# Using PowerShell
$filePath = "data\abdoun_merged_properties.csv"
$fileBytes = [System.IO.File]::ReadAllBytes($filePath)
$fileContent = [System.Convert]::ToBase64String($fileBytes)

$boundary = [System.Guid]::NewGuid().ToString()
$bodyLines = @(
    "--$boundary",
    "Content-Disposition: form-data; name=`"file`"; filename=`"abdoun_merged_properties.csv`"",
    "Content-Type: text/csv",
    "",
    [System.Text.Encoding]::UTF8.GetString($fileBytes),
    "--$boundary--"
) -join "`r`n"

Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/import-csv?geocode_missing=false" `
  -Method POST `
  -ContentType "multipart/form-data; boundary=$boundary" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($bodyLines))
```

**Expected Response:**
```json
{
  "created": 100
}
```

---

## Automated Testing Script

Run the automated test script:

```powershell
# Make sure server is running first
uvicorn app.main:app --reload

# In another terminal, run the test script
python scripts/test_endpoints.py
```

The script will test all endpoints and provide a summary.

---

## Using FastAPI Interactive Docs

The easiest way to test endpoints is using the built-in Swagger UI:

1. Start the server: `uvicorn app.main:app --reload`
2. Open browser: http://127.0.0.1:8000/docs
3. Click on any endpoint to expand it
4. Click "Try it out"
5. Fill in parameters/request body
6. Click "Execute"
7. View the response

---

## Common Test Scenarios

### Test 1: List first 10 properties
```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/properties?limit=10" | ConvertFrom-Json | ConvertTo-Json -Depth 10
```

### Test 2: Get property with ID 1
```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/properties/1" | ConvertFrom-Json | ConvertTo-Json -Depth 10
```

### Test 3: Search properties in Amman area
```powershell
$body = @{
    mode = "bounds"
    bounds = @{
        min_lng = 35.8
        min_lat = 31.9
        max_lng = 35.95
        max_lat = 32.0
    }
    limit = 20
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/search" -Method POST -ContentType "application/json" -Body $body | ConvertFrom-Json | ConvertTo-Json -Depth 10
```

---

## Error Responses

### 404 Not Found
```json
{
  "detail": "Property not found"
}
```

### 422 Validation Error
```json
{
  "detail": [
    {
      "loc": ["body", "bounds", "min_lng"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## Notes

- All coordinates use WGS84 (SRID 4326)
- Bounds search uses `ST_Intersects` (properties that intersect the bounding box)
- Polygon search uses `ST_Within` (properties completely within the polygon)
- The `location_name` field contains human-readable location text (e.g., "Dabouq - Amman")
- The `location` geometry field is used for spatial queries

