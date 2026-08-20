"""
Setup NASA Earthdata .netrc and .urs_cookies for GES DISC access.
Required for authenticated HDF5/NetCDF4 file downloads from GES DISC.
"""
import os
from pathlib import Path

home = Path.home()

# .netrc
netrc = home / ".netrc"
entry = "machine urs.earthdata.nasa.gov login harishraghav346 password 727823TUad@36\n"

if netrc.exists():
    content = netrc.read_text()
    if "urs.earthdata.nasa.gov" in content:
        print(".netrc already has Earthdata entry — updating...")
        lines = [l for l in content.splitlines() if "urs.earthdata.nasa.gov" not in l]
        content = "\n".join(lines) + "\n" + entry
    else:
        content = content + entry
else:
    content = entry

netrc.write_text(content)
# Secure permissions (important on Unix; on Windows this is advisory)
try:
    import stat
    netrc.chmod(stat.S_IRUSR | stat.S_IWUSR)
except Exception:
    pass
print(f".netrc written: {netrc}")

# .urs_cookies (empty file, required by wget/curl NASA redirects)
cookies = home / ".urs_cookies"
if not cookies.exists():
    cookies.write_text("")
print(f".urs_cookies: {cookies}")

# Verify
print("\nVerification:")
print(netrc.read_text().replace("727823TUad@36", "***REDACTED***"))
