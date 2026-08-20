"""Quick validation: extract terrain attributes at all 8 CWC station locations from the downloaded DEM."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path("pipeline")))

import yaml
from src.downloaders.srtm import SRTMDownloader
from src.utils.cache import CacheManager
from src.utils.logger import DownloadLogger

config = yaml.safe_load(open("pipeline/config.yaml"))
from pathlib import Path

# Resolve paths
for k in config["paths"]:
    p = Path(config["paths"][k])
    if not p.is_absolute():
        config["paths"][k] = str(Path("pipeline") / p)

d = SRTMDownloader(config, CacheManager(Path(config["paths"]["logs_dir"])/"cache"),
                   DownloadLogger(Path(config["paths"]["logs_dir"])/"dl.csv"))

dem_path   = Path(config["paths"]["raw_dir"]) / "srtm" / "cauvery_dem.tif"
slope_path = Path(config["paths"]["raw_dir"]) / "srtm" / "slope.tif"

if not dem_path.exists():
    print("ERROR: DEM not found:", dem_path)
    sys.exit(1)

if not slope_path.exists():
    print("Computing slope...")
    d.compute_terrain_attributes(dem_path, dem_path.parent)

station_ids    = [s["id"] for s in config["stations"]]
station_coords = [(s["lat"], s["lon"]) for s in config["stations"]]

df = d.extract_station_terrain(dem_path, slope_path, station_ids, station_coords)
d.save_station_terrain(df, Path(config["paths"]["processed_dir"]))

print("\n=== Station Terrain Attributes ===")
print(df.to_string(index=False))
nan_count = df["elevation_m"].isna().sum()
print(f"\nStations with NaN elevation: {nan_count}/{len(df)}")
if nan_count == 0:
    print("PASS: All stations have valid terrain data")
else:
    print(f"WARNING: {nan_count} stations outside DEM extent")
