"""Debug cdsapi config parsing."""
from cdsapi.api import read_config, get_url_key_verify
import os

path = os.path.expanduser("~/.cdsapirc")
print(f"File exists: {os.path.exists(path)}")
print(f"File path  : {path}")
print(f"File bytes (hex first 6): {open(path,'rb').read(6).hex()}")
print()

config = read_config(path)
print(f"Parsed config keys: {list(config.keys())}")
print(f"url: {repr(config.get('url'))}")
print(f"key: {repr(config.get('key'))}")
print()

try:
    url, key, verify = get_url_key_verify(None, None, None)
    print(f"get_url_key_verify OK")
    print(f"  url: {url}")
    print(f"  key: {key[:8]}...")
    print(f"  verify: {verify}")
except Exception as e:
    print(f"get_url_key_verify FAILED: {e}")
