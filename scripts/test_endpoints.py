"""
Script to test all API endpoints
Run this after starting the FastAPI server with: uvicorn app.main:app --reload
"""
import sys
import requests
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils.status_codes import HTTPStatus

# Fix Windows console encoding for emojis
if sys.platform == 'win32':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

BASE_URL = "http://127.0.0.1:8000/api/v1"


def test_list_properties():
    """Test GET /api/v1/properties"""
    print("\n" + "="*60)
    print("TEST 1: List Properties (GET /api/v1/properties)")
    print("="*60)
    
    # Test with default parameters
    response = requests.get(f"{BASE_URL}/properties")
    print(f"Status: {response.status_code}")
    first_property_id = None
    if response.status_code == HTTPStatus.OK:
        data = response.json()
        print(f"✅ Success! Found {data['total']} properties")
        print(f"   Page: {data.get('page', 'N/A')}, PageSize: {data.get('pageSize', 'N/A')}")
        if data.get('data'):
            first_property_id = data['data'][0]['id']
            print(f"   First property: {data['data'][0]['title']} (ID: {first_property_id})")
    else:
        print(f"❌ Error: {response.text}")
    
    # Test with pagination
    print("\n--- Testing pagination (page=1, pageSize=5) ---")
    response = requests.get(f"{BASE_URL}/properties?page=1&pageSize=5")
    if response.status_code == HTTPStatus.OK:
        data = response.json()
        print(f"✅ Found {len(data.get('data', []))} properties (pageSize=5)")
        print(f"   Page: {data.get('page')}, Total: {data.get('total')}")
    
    return response.status_code == HTTPStatus.OK, first_property_id


def test_get_property_detail(property_id: int = 1):
    """Test GET /api/v1/properties/{property_id}"""
    print("\n" + "="*60)
    print(f"TEST 2: Get Property Detail (GET /api/v1/properties/{property_id})")
    print("="*60)
    
    response = requests.get(f"{BASE_URL}/properties/{property_id}")
    print(f"Status: {response.status_code}")
    if response.status_code == HTTPStatus.OK:
        data = response.json()
        print("✅ Success!")
        print(f"   ID: {data['id']}")
        print(f"   Title: {data['title']}")
        print(f"   Location: {data.get('location_name', 'N/A')}")
        print(f"   Coordinates: ({data.get('latitude')}, {data.get('longitude')})")
        print(f"   Price: {data.get('selling_price_amount')} {data.get('selling_price_currency')}")
        print(f"   Bedrooms: {data.get('bedrooms')}, Bathrooms: {data.get('bathrooms')}")
    elif response.status_code == HTTPStatus.NOT_FOUND:
        print(f"⚠️  Property {property_id} not found")
    else:
        print(f"❌ Error: {response.text}")
    
    return response.status_code == HTTPStatus.OK


def test_search_with_filters():
    """Test GET /api/v1/properties with filters"""
    print("\n" + "="*60)
    print("TEST 3: Search Properties with Filters (GET /api/v1/properties)")
    print("="*60)
    
    # Test with status filter
    print("\n--- Testing status filter (status=buy) ---")
    response = requests.get(f"{BASE_URL}/properties?status=buy&pageSize=5")
    if response.status_code == HTTPStatus.OK:
        data = response.json()
        print(f"✅ Found {data['total']} properties for sale")
        if data.get('data'):
            print(f"   Sample: {data['data'][0]['title']} - {data['data'][0].get('price')}")
    
    # Test with category and type
    print("\n--- Testing category and type (category=residential, type=apartments) ---")
    response = requests.get(f"{BASE_URL}/properties?category=residential&type=apartments&pageSize=5")
    if response.status_code == HTTPStatus.OK:
        data = response.json()
        print(f"✅ Found {data['total']} residential apartments")
    
    # Test with city filter
    print("\n--- Testing city filter (city=amman) ---")
    response = requests.get(f"{BASE_URL}/properties?city=amman&pageSize=5")
    if response.status_code == HTTPStatus.OK:
        data = response.json()
        print(f"✅ Found {data['total']} properties in Amman")
    
    # Test with locations filter
    print("\n--- Testing locations filter (locations=abdoun) ---")
    response = requests.get(f"{BASE_URL}/properties?locations=abdoun&pageSize=5")
    if response.status_code == HTTPStatus.OK:
        data = response.json()
        print(f"✅ Found {data['total']} properties in Abdoun")
    
    # Test with price range (budgetMin/budgetMax)
    print("\n--- Testing price range (budgetMin=100000, budgetMax=500000) ---")
    response = requests.get(f"{BASE_URL}/properties?budgetMin=100000&budgetMax=500000&pageSize=5")
    if response.status_code == HTTPStatus.OK:
        data = response.json()
        print(f"✅ Found {data['total']} properties in price range")
    
    # Test with minPrice/maxPrice aliases
    print("\n--- Testing price aliases (minPrice=100000, maxPrice=500000) ---")
    response = requests.get(f"{BASE_URL}/properties?minPrice=100000&maxPrice=500000&pageSize=5")
    if response.status_code == HTTPStatus.OK:
        data = response.json()
        print(f"✅ Found {data['total']} properties using price aliases")
    
    # Test combined filters
    print("\n--- Testing combined filters ---")
    response = requests.get(
        f"{BASE_URL}/properties"
        f"?status=buy&category=residential&type=apartments&city=amman&budgetMin=100000&budgetMax=500000&page=1&pageSize=5"
    )
    if response.status_code == HTTPStatus.OK:
        data = response.json()
        print(f"✅ Found {data['total']} properties matching all filters")
        print(f"   Page: {data.get('page')}, PageSize: {data.get('pageSize')}")
        if data.get('data'):
            prop = data['data'][0]
            print(f"   Sample: {prop.get('title')} - {prop.get('price')} - {prop.get('location')}")
    
    return response.status_code == HTTPStatus.OK


def test_search_by_bounds():
    """Test POST /api/v1/properties/geo-search with bounds"""
    print("\n" + "="*60)
    print("TEST 4: Search Properties by Bounds (POST /api/v1/properties/geo-search)")
    print("="*60)
    
    # Search for properties in Amman area (approximate bounds)
    payload = {
        "mode": "bounds",
        "bounds": {
            "min_lng": 35.8,
            "min_lat": 31.9,
            "max_lng": 35.95,
            "max_lat": 32.0
        },
        "limit": 10
    }
    
    print(f"Searching bounds: {payload['bounds']}")
    response = requests.post(
        f"{BASE_URL}/properties/geo-search",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"Status: {response.status_code}")
    if response.status_code == HTTPStatus.OK:
        data = response.json()
        print(f"✅ Success! Found {data['total']} properties in bounds")
        if data.get('items'):
            print("   Sample properties:")
            for item in data['items'][:3]:
                print(f"     - {item['title']} at ({item.get('lat')}, {item.get('lng')})")
    else:
        print(f"❌ Error: {response.text}")
    
    return response.status_code == HTTPStatus.OK


def test_search_by_polygon():
    """Test POST /api/v1/properties/geo-search with polygon"""
    print("\n" + "="*60)
    print("TEST 5: Search Properties by Polygon (POST /api/v1/properties/geo-search)")
    print("="*60)
    
    # Create a polygon around Amman city center
    payload = {
        "mode": "polygon",
        "polygon": {
            "geojson": {
                "type": "Polygon",
                "coordinates": [[
                    [35.85, 31.92],  # Southwest
                    [35.95, 31.92],  # Southeast
                    [35.95, 32.0],   # Northeast
                    [35.85, 32.0],   # Northwest
                    [35.85, 31.92]   # Close polygon
                ]]
            }
        },
        "limit": 10
    }
    
    print("Searching polygon area around Amman")
    response = requests.post(
        f"{BASE_URL}/properties/geo-search",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"Status: {response.status_code}")
    if response.status_code == HTTPStatus.OK:
        data = response.json()
        print(f"✅ Success! Found {data['total']} properties in polygon")
        if data.get('items'):
            print("   Sample properties:")
            for item in data['items'][:3]:
                print(f"     - {item['title']} at ({item.get('lat')}, {item.get('lng')})")
    else:
        print(f"❌ Error: {response.text}")
    
    return response.status_code == HTTPStatus.OK


def test_exclusive_properties():
    """Test GET /api/v1/properties/exclusive"""
    print("\n" + "="*60)
    print("TEST 6: Exclusive Properties (GET /api/v1/properties/exclusive)")
    print("="*60)
    
    # Test basic exclusive endpoint
    print("\n--- Testing exclusive properties (no filters) ---")
    response = requests.get(f"{BASE_URL}/properties/exclusive?pageSize=5")
    print(f"Status: {response.status_code}")
    if response.status_code == HTTPStatus.OK:
        data = response.json()
        print(f"✅ Found {data['total']} exclusive properties")
        if data.get('data'):
            print(f"   Sample: {data['data'][0]['title']} - {data['data'][0].get('price')}")
    
    # Test exclusive with filters
    print("\n--- Testing exclusive with filters (status=buy, city=amman, locations=abdoun) ---")
    response = requests.get(
        f"{BASE_URL}/properties/exclusive"
        f"?status=buy&city=amman&locations=abdoun&budgetMin=800000&budgetMax=2000000&pageSize=5"
    )
    if response.status_code == HTTPStatus.OK:
        data = response.json()
        print(f"✅ Found {data['total']} exclusive properties matching filters")
        if data.get('data'):
            prop = data['data'][0]
            print(f"   Sample: {prop.get('title')} - {prop.get('price')} - {prop.get('location')}")
    
    # Test exclusive filter in regular endpoint
    print("\n--- Testing exclusive=true filter in regular endpoint ---")
    response = requests.get(f"{BASE_URL}/properties?exclusive=true&pageSize=5")
    if response.status_code == HTTPStatus.OK:
        data = response.json()
        print(f"✅ Found {data['total']} exclusive properties using exclusive=true")
        if data.get('data'):
            print(f"   Sample: {data['data'][0]['title']} - {data['data'][0].get('price')}")
    
    # Test exclusive=false filter
    print("\n--- Testing exclusive=false filter ---")
    response = requests.get(f"{BASE_URL}/properties?exclusive=false&pageSize=5")
    if response.status_code == HTTPStatus.OK:
        data = response.json()
        print(f"✅ Found {data['total']} non-exclusive properties")
    
    return response.status_code == HTTPStatus.OK


def test_similar_properties(property_id: int = None):
    """Test GET /api/v1/properties/{property_id}/similar"""
    print("\n" + "="*60)
    print(f"TEST 7: Similar Properties (GET /api/v1/properties/{{id}}/similar)")
    print("="*60)
    
    # Get a property ID first if not provided
    if property_id is None:
        print("--- Getting a property ID to test similar properties ---")
        response = requests.get(f"{BASE_URL}/properties?pageSize=1")
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            if data.get('data'):
                property_id = data['data'][0]['id']
                print(f"   Using property ID: {property_id}")
            else:
                print("⚠️  No properties found to test similar properties")
                return False
        else:
            print("⚠️  Could not get property ID")
            return False
    
    # Test similar properties with default limit
    print(f"\n--- Testing similar properties for ID {property_id} (default limit) ---")
    response = requests.get(f"{BASE_URL}/properties/{property_id}/similar")
    print(f"Status: {response.status_code}")
    if response.status_code == HTTPStatus.OK:
        data = response.json()
        print(f"✅ Success! Found {data['total']} similar properties")
        print(f"   Page: {data.get('page')}, PageSize: {data.get('pageSize')}")
        if data.get('data'):
            print("   Sample similar properties:")
            for prop in data['data'][:3]:
                print(f"     - {prop.get('title')} - {prop.get('price')} - {prop.get('location')}")
    elif response.status_code == HTTPStatus.NOT_FOUND:
        print(f"⚠️  Property {property_id} not found")
        return False
    else:
        print(f"❌ Error: {response.text}")
        return False
    
    # Test similar properties with custom limit
    print(f"\n--- Testing similar properties with limit=5 ---")
    response = requests.get(f"{BASE_URL}/properties/{property_id}/similar?limit=5")
    if response.status_code == HTTPStatus.OK:
        data = response.json()
        print(f"✅ Found {len(data.get('data', []))} similar properties (limit=5)")
        print(f"   Total available: {data.get('total')}")
    
    return response.status_code == HTTPStatus.OK


def test_import_csv():
    """Test POST /api/v1/import-csv"""
    print("\n" + "="*60)
    print("TEST 6: Import CSV (POST /api/v1/import-csv)")
    print("="*60)
    
    csv_path = Path("data/abdoun_merged_properties.csv")
    if not csv_path.exists():
        print(f"⚠️  CSV file not found: {csv_path}")
        print("   Skipping CSV import test")
        return False
    
    print(f"Uploading CSV: {csv_path}")
    with open(csv_path, "rb") as f:
        files = {"file": (csv_path.name, f, "text/csv")}
        response = requests.post(
            f"{BASE_URL}/import-csv?geocode_missing=false",
            files=files
        )
    
    print(f"Status: {response.status_code}")
    if response.status_code == HTTPStatus.CREATED:
        data = response.json()
        print(f"✅ Success! Imported {data.get('created', 0)} properties")
    else:
        print(f"❌ Error: {response.text}")
    
    return response.status_code == HTTPStatus.CREATED


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("FASTAPI ENDPOINTS TEST SUITE")
    print("="*60)
    print(f"Testing API at: {BASE_URL}")
    print("\n⚠️  Make sure the FastAPI server is running!")
    print("   Start with: uvicorn app.main:app --reload")
    
    try:
        # Test if server is running
        requests.get(f"{BASE_URL}/properties?pageSize=1", timeout=5)
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Cannot connect to FastAPI server!")
        print("   Please start the server first:")
        print("   uvicorn app.main:app --reload")
        return
    
    results = []
    
    # Run all tests
    list_success, first_property_id = test_list_properties()
    results.append(("List Properties", list_success))
    
    # Use the first property ID from the list, or try a common ID if list is empty
    property_id_to_test = first_property_id if first_property_id else 1
    results.append(("Get Property Detail", test_get_property_detail(property_id_to_test)))
    results.append(("Search with Filters", test_search_with_filters()))
    results.append(("Search by Bounds", test_search_by_bounds()))
    results.append(("Search by Polygon", test_search_by_polygon()))
    results.append(("Exclusive Properties", test_exclusive_properties()))
    results.append(("Similar Properties", test_similar_properties(property_id_to_test)))
    # Skip CSV import test by default (can be slow and may create duplicates)
    # results.append(("Import CSV", test_import_csv()))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    print(f"\nTotal: {passed}/{total} tests passed")


if __name__ == "__main__":
    main()

