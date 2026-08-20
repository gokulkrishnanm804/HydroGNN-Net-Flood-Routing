"""Test NASA Earthdata auth before committing to the full GPM download."""
import os, sys, requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path("c:/Users/gokul/Downloads/new_project/.env"))

username = os.environ.get("NASA_EARTHDATA_USERNAME", "")
password = os.environ.get("NASA_EARTHDATA_PASSWORD", "")

if not username or not password:
    print("ERROR: Credentials not found in .env")
    sys.exit(1)

print(f"Testing auth for user: {username}")

# NASA Earthdata auth endpoint
auth_url = "https://urs.earthdata.nasa.gov/api/users/tokens"
session = requests.Session()
session.auth = (username, password)

try:
    resp = session.get(auth_url, timeout=15)
    if resp.status_code == 200:
        print("AUTH SUCCESS: NASA Earthdata credentials are valid.")
    elif resp.status_code == 401:
        print("AUTH FAILED: Invalid username or password (HTTP 401).")
        sys.exit(1)
    else:
        print(f"AUTH CHECK: HTTP {resp.status_code} — attempting GES DISC test...")
        # Alternative: test against GES DISC directly
        test_url = "https://gpm1.gesdisc.eosdis.nasa.gov/data/GPM_L3/GPM_3IMERGHH.07/"
        r2 = session.get(test_url, timeout=15)
        print(f"  GES DISC test: HTTP {r2.status_code}")
        if r2.status_code in (200, 302):
            print("  AUTH OK — GES DISC accessible")
        else:
            print(f"  GES DISC returned {r2.status_code}")
except Exception as e:
    print(f"Connection error: {e}")
    sys.exit(1)
