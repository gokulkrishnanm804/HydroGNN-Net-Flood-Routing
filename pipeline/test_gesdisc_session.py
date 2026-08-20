"""
Fix NASA GES DISC 401 — creates a proper Earthdata OAuth session.

The standard `requests(auth=...)` fails because GES DISC uses an OAuth redirect flow:
  1. Client requests data URL
  2. GES DISC redirects to https://urs.earthdata.nasa.gov/oauth/authorize
  3. Earthdata validates credentials and issues a cookie
  4. Earthdata redirects back to GES DISC with the cookie
  5. GES DISC delivers the file

Fix: Use a persistent requests.Session that:
  - Sets auth on the session (so it's sent to URS on the redirect)
  - Follows redirects automatically
  - Stores cookies for subsequent requests

Also checks that the GES DISC app is approved.
"""
import os, sys, requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path("c:/Users/gokul/Downloads/new_project/.env"))

USERNAME = os.environ["NASA_EARTHDATA_USERNAME"]
PASSWORD = os.environ["NASA_EARTHDATA_PASSWORD"]

print(f"Testing Earthdata session for: {USERNAME}")

# Build the proper Earthdata session
session = requests.Session()
session.auth = (USERNAME, PASSWORD)

# Test URL: a small GPM file listing (directory index)
test_url = "https://gpm1.gesdisc.eosdis.nasa.gov/data/GPM_L3/GPM_3IMERGHH.07/2018/001/"

resp = session.get(test_url, timeout=30, allow_redirects=True)
print(f"  Final URL      : {resp.url}")
print(f"  Status code    : {resp.status_code}")
print(f"  Content-Type   : {resp.headers.get('Content-Type','')}")
print(f"  Cookies stored : {len(session.cookies)}")

if resp.status_code == 200:
    # Try to find any HDF5 filename in the listing
    import re
    files = re.findall(r'3B-HHR\.MS\.MRG\.3IMERG\.[^"<>]+\.HDF5', resp.text)
    print(f"  Files found    : {len(files)}")
    if files:
        print(f"  Sample file    : {files[0]}")
    print("\nSESSION OK - Download should work")
elif resp.status_code == 401:
    print("\nSTILL 401 — App not approved.")
    print("ACTION REQUIRED:")
    print("  1. Go to: https://urs.earthdata.nasa.gov/approve_app?client_id=e2WVk8Pw6weeLUKZYOxvTQ")
    print("  2. Log in with harishraghav346 and approve 'NASA GESDISC DATA ARCHIVE'")
    print("  3. Re-run this script")
    sys.exit(1)
else:
    print(f"\nUnexpected status: {resp.status_code}")
    print(resp.text[:500])
    sys.exit(1)
