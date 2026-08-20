"""Phase 1: Environment verification script."""
import os, sys, shutil, json
from pathlib import Path

ROOT = Path("c:/Users/gokul/Downloads/new_project")
report = {}

# Python
report["python"] = sys.version

# PyTorch
try:
    import torch
    report["torch"] = torch.__version__
    report["cuda_available"] = torch.cuda.is_available()
    report["cuda_device"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "N/A"
except ImportError:
    report["torch"] = "MISSING"

# Packages
pkgs = ["torch_geometric","numpy","pandas","scipy","xarray","netCDF4","h5py",
        "rasterio","geopandas","tqdm","requests","onnx","cdsapi","elevation"]
report["packages"] = {}
for pkg in pkgs:
    try:
        m = __import__(pkg)
        report["packages"][pkg] = getattr(m, "__version__", "installed")
    except ImportError:
        report["packages"][pkg] = "MISSING"

# Disk
total, used, free = shutil.disk_usage("c:/")
report["disk"] = {"total_gb": round(total/1e9,1), "free_gb": round(free/1e9,1)}

# Credentials
creds = {}
for key in ["NASA_EARTHDATA_USERNAME","NASA_EARTHDATA_PASSWORD","CDSAPI_KEY"]:
    creds[key] = "SET" if os.environ.get(key) else "NOT_SET"

env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        if k in creds:
            creds[k] = "SET_IN_DOTENV"
report["credentials"] = creds

cds_rc = Path.home() / ".cdsapirc"
report["cds_rc_exists"] = cds_rc.exists()

# Print
print(json.dumps(report, indent=2))

# Human summary
print("\n=== ENVIRONMENT SUMMARY ===")
print(f"Python        : {report['python'][:10]}")
print(f"PyTorch       : {report.get('torch','?')}")
print(f"CUDA          : {report.get('cuda_available','?')}")
print(f"Disk Free     : {report['disk']['free_gb']} GB")

missing_pkgs = [k for k,v in report["packages"].items() if v == "MISSING"]
if missing_pkgs:
    print(f"MISSING pkgs  : {missing_pkgs}")
else:
    print("All packages  : OK")

missing_creds = [k for k,v in report["credentials"].items() if v == "NOT_SET"]
if missing_creds:
    print(f"MISSING creds : {missing_creds}")
else:
    print("Credentials   : OK")
