"""Test Copernicus CDS API connection before ERA5 download."""
import sys
import cdsapi

print("Testing Copernicus CDS API connection...")
try:
    c = cdsapi.Client(quiet=True)
    print(f"  CDS URL  : {c.url}")
    print(f"  CDS UID  : {c.key.split(':')[0] if ':' in str(c.key) else '(key loaded)'}")

    # Minimal test request: 1 variable, 1 day, Cauvery bbox — tiny file
    result = c.retrieve(
        "reanalysis-era5-single-levels",
        {
            "product_type": "reanalysis",
            "variable":     ["2m_temperature"],
            "year":         "2018",
            "month":        "01",
            "day":          "01",
            "time":         ["00:00"],
            "area":         [13.5, 75.0, 10.0, 80.5],   # N, W, S, E
            "format":       "netcdf",
        },
    )
    import tempfile, os
    tmp = tempfile.mktemp(suffix=".nc")
    result.download(tmp)
    size_kb = os.path.getsize(tmp) / 1024
    os.unlink(tmp)
    print(f"\nCDS CONNECTION OK")
    print(f"  Test file size: {size_kb:.0f} KB")
    print(f"  ERA5 download is ready to start.")
except Exception as e:
    print(f"\nCDS ERROR: {e}")
    sys.exit(1)
