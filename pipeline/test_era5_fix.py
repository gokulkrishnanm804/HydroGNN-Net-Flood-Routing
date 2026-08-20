"""Test ERA5 monthly download with corrected API v2 fields."""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path("pipeline")))

from dotenv import load_dotenv
load_dotenv(".env")

import yaml
config = yaml.safe_load(open("pipeline/config.yaml"))
for k in config["paths"]:
    p = Path(config["paths"][k])
    if not p.is_absolute():
        config["paths"][k] = str(Path("pipeline") / p)

from src.downloaders.era5 import ERA5Downloader
from src.utils.cache import CacheManager
from src.utils.logger import DownloadLogger

cache  = CacheManager(Path(config["paths"]["logs_dir"]) / "cache")
dl_log = DownloadLogger(Path(config["paths"]["logs_dir"]) / "downloads.csv")

d = ERA5Downloader(cache, dl_log, config)

station_ids    = [s["id"]            for s in config["stations"]]
station_coords = [(s["lat"], s["lon"]) for s in config["stations"]]

# Test: download just January 2018
nc_path = Path(config["paths"]["raw_dir"]) / "era5" / "test_era5_2018_01.nc"
print(f"Requesting ERA5 2018-01 with fixed API fields...")
print(f"  Variables: {config['era5']['variables']}")
print(f"  data_format: {config['era5']['data_format']}")

try:
    d.download_month(2018, 1, nc_path)
    size_mb = nc_path.stat().st_size / 1e6
    print(f"\nDOWNLOAD OK: {size_mb:.1f} MB")

    print("Extracting station values...")
    df = d.extract_station_values(nc_path, station_ids, station_coords)
    print(f"Extracted: {len(df):,} rows x {len(df.columns)} columns")
    print(f"Stations: {df['station_id'].unique().tolist() if 'station_id' in df.columns else 'N/A'}")
    print(f"Time range: {df['timestamp'].min()} → {df['timestamp'].max()}")
    print("\nERA5 FIX CONFIRMED. Safe to launch full download.")

    nc_path.unlink()
    print("Test file deleted.")
except Exception as e:
    print(f"\nFAILED: {e}")
    sys.exit(1)
