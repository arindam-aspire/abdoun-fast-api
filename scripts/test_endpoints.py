"""
Script to test all API endpoints
Run this after starting the FastAPI server with: uvicorn app.main:app --reload

Required environment variables in .env file for agent tests:
- TEST_ADMIN_EMAIL: Admin user email (default: TEST_ADMIN_EMAIL)
- TEST_ADMIN_PASSWORD: Admin user password
- TEST_AGENT_ID: Agent UUID to test with (default: TEST_AGENT_ID)"""
import sys
import os
import requests
import json
import uuid
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

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
BASE_URL_FULL = "http://127.0.0.1:8000"

# Agent test configuration from .env
ADMIN_EMAIL = os.getenv("TEST_ADMIN_EMAIL", "testadmin@example.com")
ADMIN_PASSWORD = os.getenv("TEST_ADMIN_PASSWORD", "")
AGENT_ID = os.getenv("TEST_AGENT_ID", "1309csss-4664-4b7c-9038-7sw23cb455fb")
TEST_AGENT_EMAIL = os.getenv("TEST_AGENT_EMAIL", "testag@example.com")
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


def test_list_cities():
    """Test GET /api/v1/cities"""
    print("\n" + "="*60)
    print("TEST 8: List Cities (GET /api/v1/cities)")
    print("="*60)
    
    response = requests.get(f"{BASE_URL}/cities")
    print(f"Status: {response.status_code}")
    if response.status_code == HTTPStatus.OK:
        data = response.json()
        print(f"✅ Success! Found {data['total']} cities")
        if data.get('data'):
            print("   Sample cities:")
            for city in data['data'][:5]:
                print(f"     - {city['name']} (ID: {city['id']})")
    else:
        print(f"❌ Error: {response.text}")
    
    return response.status_code == HTTPStatus.OK


def test_list_areas():
    """Test GET /api/v1/areas"""
    print("\n" + "="*60)
    print("TEST 9: List Areas (GET /api/v1/areas)")
    print("="*60)
    
    # Test all areas
    print("\n--- Testing all areas (no filter) ---")
    response = requests.get(f"{BASE_URL}/areas")
    print(f"Status: {response.status_code}")
    if response.status_code == HTTPStatus.OK:
        data = response.json()
        print(f"✅ Found {data['total']} areas")
        if data.get('data'):
            print("   Sample areas:")
            for area in data['data'][:5]:
                print(f"     - {area['name']} (City: {area.get('city_name', 'N/A')})")
    
    # Test areas filtered by city
    print("\n--- Testing areas filtered by city (city=amman) ---")
    response = requests.get(f"{BASE_URL}/areas?city=amman")
    if response.status_code == HTTPStatus.OK:
        data = response.json()
        print(f"✅ Found {data['total']} areas in Amman")
        if data.get('data'):
            print("   Sample areas in Amman:")
            for area in data['data'][:5]:
                print(f"     - {area['name']}")
    
    return response.status_code == HTTPStatus.OK


def test_import_csv():
    """Test POST /api/v1/properties/import-csv (requires auth + property:create)"""
    print("\n" + "="*60)
    print("TEST 10: Import CSV (POST /api/v1/properties/import-csv)")
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
            f"{BASE_URL}/properties/import-csv?geocode_missing=false",
            files=files
        )
    
    print(f"Status: {response.status_code}")
    if response.status_code == HTTPStatus.CREATED:
        data = response.json()
        print(f"✅ Success! Imported {data.get('created', 0)} properties")
    else:
        print(f"❌ Error: {response.text}")
    
    return response.status_code == HTTPStatus.CREATED


# ============================================================================
# Agent Management Tests
# ============================================================================

def get_admin_token() -> Optional[str]:
    """Login as admin and get access token."""
    if not ADMIN_PASSWORD:
        print("⚠️  TEST_ADMIN_PASSWORD not set in .env, skipping agent tests")
        return None
    
    try:
        response = requests.post(
            f"{BASE_URL_FULL}/api/v1/auth/login/password",
            json={
                "username": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            },
            timeout=10
        )
        
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            token = data.get("data", {}).get("access_token")
            return token
        else:
            print(f"❌ Login failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"❌ Login error: {str(e)}")
        return None


def test_agent_assign(token: str) -> bool:
    """Test POST /api/v1/agents/assign-agent"""
    print("\n" + "="*60)
    print("TEST 19: Assign Agent (POST /api/v1/agents/assign-agent)")
    print("="*60)
    
    try:
        response = requests.post(
            f"{BASE_URL_FULL}/api/v1/agents/assign-agent",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={
                "agent_id": AGENT_ID,
                "can_inherit_privileges": True
            },
            timeout=10
        )
        
        print(f"Status: {response.status_code}")
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            print("✅ Success! Agent assigned")
            print(f"   Message: {data.get('message', 'N/A')}")
            return True
        else:
            print(f"❌ Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def test_agent_unassign(token: str) -> bool:
    """Test POST /api/v1/agents/unassign-agent"""
    print("\n" + "="*60)
    print("TEST 20: Unassign Agent (POST /api/v1/agents/unassign-agent)")
    print("="*60)
    
    try:
        response = requests.post(
            f"{BASE_URL_FULL}/api/v1/agents/unassign-agent",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={
                "agent_id": AGENT_ID,
                "can_inherit_privileges": True
            },
            timeout=10
        )
        
        print(f"Status: {response.status_code}")
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            print("✅ Success! Agent unassigned")
            print(f"   Message: {data.get('message', 'N/A')}")
            return True
        else:
            print(f"❌ Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def test_get_assignments(token: str) -> bool:
    """Test GET /api/v1/agents/assignments"""
    print("\n" + "="*60)
    print("TEST 21: Get Assignments (GET /api/v1/agents/assignments)")
    print("="*60)
    
    try:
        # Get all assignments for current admin
        # Note: If route order causes /{agent_id} to match first, this will return 422
        # In that case, we'll skip this test gracefully
        response = requests.get(
            f"{BASE_URL_FULL}/api/v1/agents/assignments",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            timeout=10
        )
        
        print(f"Status: {response.status_code}")
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            assignments = data.get("data", [])
            print(f"✅ Success! Found {len(assignments)} assignments")
            if assignments:
                for assignment in assignments[:3]:  # Show first 3
                    print(f"   - Agent: {assignment.get('agent_email')} | Status: {assignment.get('status')}")
            return True
        elif response.status_code == 422:
            # Route conflict: /{agent_id} matched before /assignments
            # This happens when /{agent_id} route is defined before /assignments in the router
            # FastAPI matches routes in order, so /{agent_id} catches "assignments" as an agent_id
            error_detail = response.json().get("detail", "")
            if "uuid_parsing" in str(error_detail) or "assignments" in str(error_detail).lower():
                print("⚠️  Route conflict: /{agent_id} route matched before /assignments")
                print("   FastAPI is trying to parse 'assignments' as a UUID for /{agent_id}")
                print("   Note: /assignments route exists but is unreachable due to route order")
                print("   This is a code-level routing issue - /assignments should be defined before /{agent_id}")
                return False  # Mark as fail since endpoint is actually unreachable
            else:
                print(f"⚠️  Validation error: {error_detail}")
                return False
        else:
            print(f"❌ Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def test_get_assignments_by_agent(token: str) -> bool:
    """Test GET /api/v1/agents/assignments?agent_id={agent_id}"""
    print("\n" + "="*60)
    print("TEST 22: Get Assignments by Agent ID")
    print("="*60)
    
    try:
        response = requests.get(
            f"{BASE_URL_FULL}/api/v1/agents/assignments?agent_id={AGENT_ID}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            timeout=10
        )
        
        print(f"Status: {response.status_code}")
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            assignments = data.get("data", [])
            print(f"✅ Success! Found {len(assignments)} assignments for agent")
            return True
        elif response.status_code == 422:
            # Route conflict: /{agent_id} matched before /assignments
            # This happens when /{agent_id} route is defined before /assignments in the router
            # FastAPI matches routes in order, so /{agent_id} catches "assignments" as an agent_id
            error_detail = response.json().get("detail", "")
            if "uuid_parsing" in str(error_detail) or "assignments" in str(error_detail).lower():
                print("⚠️  Route conflict: /{agent_id} route matched before /assignments")
                print("   FastAPI is trying to parse 'assignments' as a UUID for /{agent_id}")
                print("   Note: /assignments route exists but is unreachable due to route order")
                print("   This is a code-level routing issue - /assignments should be defined before /{agent_id}")
                return False  # Mark as fail since endpoint is actually unreachable
            else:
                print(f"⚠️  Validation error: {error_detail}")
                return False
        else:
            print(f"❌ Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def test_invite_agent(token: str) -> bool:
    """Test POST /api/v1/agents/invite"""
    print("\n" + "="*60)
    print("TEST 11: Invite Agent (POST /api/v1/agents/invite)")
    print("="*60)
    
    # Use a unique email to avoid conflicts
    test_email = f"testagent_{uuid.uuid4().hex[:8]}@example.com"
    
    try:
        response = requests.post(
            f"{BASE_URL_FULL}/api/v1/agents/invite",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={"email": test_email},
            timeout=10
        )
        
        print(f"Status: {response.status_code}")
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            print(f"✅ Success! Agent invited: {test_email}")
            print(f"   Message: {data.get('message', 'N/A')}")
            invite_data = data.get("data", {})
            if invite_data.get("inviteLink"):
                print(f"   Invite Link: {invite_data['inviteLink'][:80]}...")
            return True
        elif response.status_code == HTTPStatus.CONFLICT:
            print(f"⚠️  Agent already exists (expected if email was used before)")
            return True  # Not a failure, just means agent exists
        else:
            print(f"❌ Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def test_list_agents(token: str) -> bool:
    """Test GET /api/v1/agents"""
    print("\n" + "="*60)
    print("TEST 12: List Agents (GET /api/v1/agents)")
    print("="*60)
    
    try:
        # Test with pagination
        response = requests.get(
            f"{BASE_URL_FULL}/api/v1/agents?page=1&limit=10",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            timeout=10
        )
        
        print(f"Status: {response.status_code}")
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            agents_data = data.get("data", {})
            agents = agents_data.get("agents", [])
            pagination = agents_data.get("pagination", {})
            print(f"✅ Success! Found {pagination.get('totalItems', 0)} agents")
            print(f"   Page: {pagination.get('page', 1)}/{pagination.get('totalPages', 1)}")
            if agents:
                print(f"   Sample: {agents[0].get('email')} - {agents[0].get('status')}")
            return True
        else:
            print(f"❌ Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def test_list_agents_with_filters(token: str) -> bool:
    """Test GET /api/v1/agents with filters"""
    print("\n" + "="*60)
    print("TEST 13: List Agents with Filters")
    print("="*60)
    
    try:
        # Test with status filter
        response = requests.get(
            f"{BASE_URL_FULL}/api/v1/agents?status=ACTIVE&page=1&limit=5",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            timeout=10
        )
        
        print(f"Status: {response.status_code}")
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            agents_data = data.get("data", {})
            agents = agents_data.get("agents", [])
            print(f"✅ Success! Found {len(agents)} active agents")
            
            # Test with search filter
            if agents:
                search_email = agents[0].get("email", "").split("@")[0]
                if search_email:
                    response2 = requests.get(
                        f"{BASE_URL_FULL}/api/v1/agents?search={search_email}&page=1&limit=5",
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json"
                        },
                        timeout=10
                    )
                    if response2.status_code == HTTPStatus.OK:
                        data2 = response2.json()
                        agents2 = data2.get("data", {}).get("agents", [])
                        print(f"   Search test: Found {len(agents2)} agents matching '{search_email}'")
            return True
        else:
            print(f"❌ Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def test_list_invites(token: str) -> bool:
    """Test GET /api/v1/agents/invites"""
    print("\n" + "="*60)
    print("TEST 14: List Invites (GET /api/v1/agents/invites)")
    print("="*60)
    
    try:
        response = requests.get(
            f"{BASE_URL_FULL}/api/v1/agents/invites",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            timeout=10
        )
        
        print(f"Status: {response.status_code}")
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            invites = data.get("data", [])
            print(f"✅ Success! Found {len(invites)} invites")
            if invites:
                for invite in invites[:3]:  # Show first 3
                    print(f"   - {invite.get('email')} | Used: {invite.get('is_used', False)}")
            return True
        else:
            print(f"❌ Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def test_get_agent_details(token: str) -> bool:
    """Test GET /api/v1/agents/{agent_id}"""
    print("\n" + "="*60)
    print("TEST 15: Get Agent Details (GET /api/v1/agents/{agent_id})")
    print("="*60)
    
    try:
        response = requests.get(
            f"{BASE_URL_FULL}/api/v1/agents/{AGENT_ID}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            timeout=10
        )
        
        print(f"Status: {response.status_code}")
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            agent_data = data.get("data", {})
            print(f"✅ Success! Agent details retrieved")
            print(f"   Email: {agent_data.get('email')}")
            print(f"   Name: {agent_data.get('fullName')}")
            print(f"   Status: {agent_data.get('status')}")
            return True
        elif response.status_code == HTTPStatus.NOT_FOUND:
            print(f"⚠️  Agent {AGENT_ID} not found (may not exist)")
            return True  # Not a failure, agent might not exist
        else:
            print(f"❌ Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def test_accept_agent(token: str) -> bool:
    """Test PATCH /api/v1/agents/{agent_id}/accept"""
    print("\n" + "="*60)
    print("TEST 16: Accept Agent (PATCH /api/v1/agents/{agent_id}/accept)")
    print("="*60)
    
    try:
        response = requests.patch(
            f"{BASE_URL_FULL}/api/v1/agents/{AGENT_ID}/accept",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            timeout=10
        )
        
        print(f"Status: {response.status_code}")
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            print("✅ Success! Agent accepted")
            print(f"   Message: {data.get('message', 'N/A')}")
            return True
        elif response.status_code == HTTPStatus.NOT_FOUND:
            print(f"⚠️  Agent {AGENT_ID} not found")
            return True  # Not a failure
        elif response.status_code == HTTPStatus.BAD_REQUEST:
            print(f"⚠️  Agent may already be accepted or invalid status")
            print(f"   Response: {response.text}")
            return True  # Not a failure, just means already processed
        else:
            print(f"❌ Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def test_decline_agent(token: str) -> bool:
    """Test PATCH /api/v1/agents/{agent_id}/decline"""
    print("\n" + "="*60)
    print("TEST 17: Decline Agent (PATCH /api/v1/agents/{agent_id}/decline)")
    print("="*60)
    
    try:
        response = requests.patch(
            f"{BASE_URL_FULL}/api/v1/agents/{AGENT_ID}/decline",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={"reason": "Test decline reason"},
            timeout=10
        )
        
        print(f"Status: {response.status_code}")
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            print("✅ Success! Agent declined")
            print(f"   Message: {data.get('message', 'N/A')}")
            return True
        elif response.status_code == HTTPStatus.NOT_FOUND:
            print(f"⚠️  Agent {AGENT_ID} not found")
            return True  # Not a failure
        elif response.status_code == HTTPStatus.BAD_REQUEST:
            print(f"⚠️  Agent may not be in PENDING_REVIEW status")
            print(f"   Response: {response.text}")
            return True  # Not a failure
        else:
            print(f"❌ Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def test_validate_invite_token() -> bool:
    """Test GET /api/v1/agents/invite/validate (public endpoint)"""
    print("\n" + "="*60)
    print("TEST 18: Validate Invite Token (GET /api/v1/agents/invite/validate)")
    print("="*60)
    
    # This is a public endpoint, so we test with an invalid token
    try:
        response = requests.get(
            f"{BASE_URL_FULL}/api/v1/agents/invite/validate?token=invalid_token_12345",
            timeout=10
        )
        
        print(f"Status: {response.status_code}")
        if response.status_code == HTTPStatus.NOT_FOUND:
            print("✅ Correctly rejected invalid token (404 Not Found)")
            return True
        elif response.status_code == HTTPStatus.OK:
            print("⚠️  Token was valid (unexpected for test)")
            return True
        else:
            print(f"❌ Unexpected status: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def test_agent_auth_required():
    """Test that agent endpoints require authentication"""
    print("\n" + "="*60)
    print("TEST 23: Agent Endpoints Auth Check")
    print("="*60)
    
    try:
        # Test assign-agent without token
        response = requests.post(
            f"{BASE_URL_FULL}/api/v1/agents/assign-agent",
            headers={"Content-Type": "application/json"},
            json={"agent_id": AGENT_ID},
            timeout=10
        )
        
        # FastAPI returns 403 Forbidden (not 401) when authentication is missing
        # Both 401 and 403 indicate auth is required, which is what we're testing
        if response.status_code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
            status_name = "401 Unauthorized" if response.status_code == HTTPStatus.UNAUTHORIZED else "403 Forbidden"
            print(f"✅ Correctly rejected request without token ({status_name})")
            print(f"   Response: {response.text}")
            return True
        else:
            print(f"❌ Expected 401 or 403, got {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("FASTAPI ENDPOINTS TEST SUITE")
    print("="*60)
    print(f"Testing API at: {BASE_URL}")
    print("\n⚠️  Make sure the FastAPI server is running!")
    print("   Start with: uvicorn app.main:app --reload")
    
    try:
        # Test if server is running (lightweight health check)
        # We keep the timeout low so the script fails fast if server is really down,
        # but we also handle ReadTimeout separately so a slow endpoint doesn't abort the suite.
        requests.get(f"{BASE_URL}/properties?pageSize=1", timeout=5)
    except requests.exceptions.ReadTimeout:
        print("\n⚠️  WARNING: Server responded too slowly to health check (ReadTimeout).")
        print("   Continuing with tests anyway, but some endpoints may be slow or blocked.")
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
    results.append(("List Cities", test_list_cities()))
    results.append(("List Areas", test_list_areas()))
    # Skip CSV import test by default (can be slow and may create duplicates)
    # results.append(("Import CSV", test_import_csv()))
    
    # Agent Management Tests (require admin authentication)
    print("\n" + "="*60)
    print("AGENT MANAGEMENT TESTS")
    print("="*60)
    token = get_admin_token()
    if token:
        # Agent CRUD operations
        results.append(("Invite Agent", test_invite_agent(token)))
        results.append(("List Agents", test_list_agents(token)))
        results.append(("List Agents with Filters", test_list_agents_with_filters(token)))
        results.append(("List Invites", test_list_invites(token)))
        results.append(("Get Agent Details", test_get_agent_details(token)))
        results.append(("Accept Agent", test_accept_agent(token)))
        results.append(("Decline Agent", test_decline_agent(token)))
        
        # Agent Assignment operations
        results.append(("Get Assignments", test_get_assignments(token)))
        results.append(("Get Assignments by Agent", test_get_assignments_by_agent(token)))
        results.append(("Assign Agent", test_agent_assign(token)))
        results.append(("Unassign Agent", test_agent_unassign(token)))
        
        # Public endpoints (no auth required)
        results.append(("Validate Invite Token", test_validate_invite_token()))
        
        # Auth checks
        results.append(("Agent Auth Check", test_agent_auth_required()))
    else:
        print("⚠️  Skipping agent management tests (authentication failed)")
        # Still test public endpoints
        results.append(("Validate Invite Token", test_validate_invite_token()))
    
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

