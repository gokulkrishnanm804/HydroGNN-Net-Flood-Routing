"""Test optimized GPM downloader on 1 day."""
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

from src.downloaders.gpm_imerg import GPMOptimizedDownloader
from src.utils.cache import CacheManager
from src.utils.logger import DownloadLogger
from datetime import date

# Use a clean temp folder for testing
proc_dir = Path("pipeline/dataset/processed_test")
proc_dir.mkdir(parents=True, exist_ok=True)
config["paths"]["processed_dir"] = str(proc_dir)

cache  = CacheManager(Path(config["paths"]["logs_dir"]) / "cache_test")
dl_log = DownloadLogger(Path(config["paths"]["logs_dir"]) / "downloads_test.csv")

d = GPMOptimizedDownloader(cache, dl_log, config)
station_ids    = [s["id"]            for s in config["stations"]]
station_coords = [(s["lat"], s["lon"]) for s in config["stations"]]

# Test 1 day: June 1, 2018
start = date(2018, 6, 1)
end = date(2018, 6, 1)

print("Starting GPM test run for 1 day...")
d.run_optimized(start, end, station_ids, station_coords)

print("Test run finished. Checking output files:")
for f in proc_dir.glob("gpm_*.parquet"):
    import pandas as pd
    df = pd.read_parquet(f)
    print(f"  {f.name}: {len(df)} rows")
