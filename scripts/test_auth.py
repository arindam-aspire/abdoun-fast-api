import requests
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Fix Windows console encoding for emojis
if sys.platform == 'win32':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from app.utils.status_codes import HTTPStatus

BASE_URL = "http://127.0.0.1:8000/api/v1/auth"

def test_social_login_url():
    print("\n--- Testing Social Login URL Generation ---")
    response = requests.get(f"{BASE_URL}/social-login?provider=Google")
    print(f"Status: {response.status_code}")
    if response.status_code == HTTPStatus.OK:
        url = response.json().get("data", {}).get("url")
        print(f"Success! URL: {url[:50]}...")
    else:
        print(f"Error: {response.text}")

def test_auth_endpoints():
    print("\n" + "="*60)
    print("COGNITO AUTHENTICATION TEST SUITE")
    print("="*60)
    
    try:
        # Check if server is running
        print(f"Checking connection to {BASE_URL}...")
        requests.get(f"{BASE_URL}/social-login?provider=Google", timeout=5)
        print("Connection check passed.")
    except Exception as e:
        print(f"\nERROR: Cannot connect to FastAPI server! Error: {e}")
        print("   Please start the server first: uvicorn app.main:app --reload")
        return

    test_social_login_url()
    
    print("\n[NOTE] Signup/Login tests require valid Cognito setup and manual verification.")
    print("       You can test these using Postman or by providing test credentials here.")

if __name__ == "__main__":
    test_auth_endpoints()
