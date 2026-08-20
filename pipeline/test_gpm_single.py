"""Test downloading a single GPM IMERG file to verify OAuth session fix."""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path("pipeline")))

from dotenv import load_dotenv
load_dotenv(Path("c:/Users/gokul/Downloads/new_project/.env"))

import yaml
from datetime import date

config = yaml.safe_load(open("pipeline/config.yaml"))
for k in config["paths"]:
    p = Path(config["paths"][k])
    if not p.is_absolute():
        config["paths"][k] = str(Path("pipeline") / p)

from src.downloaders.gpm_imerg import GPMIMERGDownloader
from src.utils.cache import CacheManager
from src.utils.logger import DownloadLogger

cache  = CacheManager(Path(config["paths"]["logs_dir"]) / "cache")
dl_log = DownloadLogger(Path(config["paths"]["logs_dir"]) / "downloads.csv")

gpm = GPMIMERGDownloader(cache, dl_log, config)

# Test: download just the first 30-min slot of 2018-01-01
import pandas as pd
ts = pd.Timestamp("2018-01-01 00:00:00", tz="UTC")
url = gpm.build_file_url(ts)
fname = url.split("/")[-1]
dest = Path(config["paths"]["raw_dir"]) / "gpm" / "2018" / "01" / fname

print(f"Test URL: {url}")
print(f"Dest    : {dest}")
print("Downloading single file to test OAuth fix...")

ok = gpm.download_file(url, dest, auth=gpm._auth(), source_label="GPM_IMERG_TEST")

if ok and dest.exists():
    size_mb = dest.stat().st_size / 1e6
    print(f"\nSUCCESS: {fname} ({size_mb:.1f} MB)")
    print("OAuth session fix confirmed. Ready for full download.")
else:
    print("\nFAILED: File not downloaded. Check error above.")
    sys.exit(1)
