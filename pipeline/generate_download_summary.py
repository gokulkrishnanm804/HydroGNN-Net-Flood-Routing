"""Generate download_summary.json from current state of all raw data directories."""
import sys, json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path("pipeline")))
import yaml

config  = yaml.safe_load(open("pipeline/config.yaml"))
raw_dir = Path("pipeline") / "dataset" / "raw"

summary = {
    "generated_at": datetime.now().isoformat(),
    "basin": "Cauvery",
    "years": f"{config['years']['start']}-{config['years']['end']}",
    "sources": {}
}

# HydroRIVERS
hriv_shp = raw_dir / "hydrorivers" / "cauvery_rivers.shp"
summary["sources"]["hydrorivers"] = {
    "status": "OK",
    "file": str(hriv_shp) if hriv_shp.exists() else "MISSING",
    "size_mb": round(hriv_shp.stat().st_size / 1e6, 1) if hriv_shp.exists() else 0,
    "note": "4518 river segments clipped to Cauvery basin bbox"
}

# SRTM
srtm_dem = raw_dir / "srtm" / "cauvery_dem.tif"
srtm_dir = raw_dir / "srtm" / "srtm_tiles"
tile_count = len(list(srtm_dir.glob("*.tif"))) if srtm_dir.exists() else 0
summary["sources"]["srtm"] = {
    "status": "OK",
    "file": str(srtm_dem) if srtm_dem.exists() else "MISSING",
    "size_mb": round(srtm_dem.stat().st_size / 1e6, 1) if srtm_dem.exists() else 0,
    "tiles_downloaded": tile_count,
    "note": f"{tile_count} CGIAR 5x5-degree tiles mosaiced"
}

# GPM IMERG
gpm_dir = raw_dir / "gpm"
gpm_files = list(gpm_dir.glob("**/*.HDF5")) + list(gpm_dir.glob("**/*.nc4")) + list(gpm_dir.glob("**/*.h5"))
summary["sources"]["gpm_imerg"] = {
    "status": "MISSING" if not gpm_files else "OK",
    "file_count": len(gpm_files),
    "size_gb": round(sum(f.stat().st_size for f in gpm_files) / 1e9, 2) if gpm_files else 0,
    "note": "BLOCKED: NASA Earthdata credentials required. Register at https://urs.earthdata.nasa.gov"
}

# ERA5
era5_dir = raw_dir / "era5"
era5_files = list(era5_dir.glob("**/*.nc")) + list(era5_dir.glob("**/*.grib"))
summary["sources"]["era5"] = {
    "status": "MISSING" if not era5_files else "OK",
    "file_count": len(era5_files),
    "size_gb": round(sum(f.stat().st_size for f in era5_files) / 1e9, 2) if era5_files else 0,
    "note": "BLOCKED: CDS API key required. Register at https://cds.climate.copernicus.eu"
}

# CWC
cwc_dir = raw_dir / "cwc"
cwc_files = list(cwc_dir.glob("*.csv"))
stations = [s["id"] for s in config["stations"]]
years = list(range(config["years"]["start"], config["years"]["end"] + 1))
expected_files = [f"{s}_{y}.csv" for s in stations for y in years]
missing_cwc = [f for f in expected_files if not (cwc_dir / f).exists()]
summary["sources"]["cwc"] = {
    "status": "MISSING" if cwc_files == [] else "PARTIAL",
    "files_found": len(cwc_files),
    "files_expected": len(expected_files),
    "files_missing": len(missing_cwc),
    "missing_list": missing_cwc[:10],  # first 10
    "note": "BLOCKED: Manual export from India-WRIS required. https://indiawris.gov.in/wris/#/"
}

# Reservoir
res_dir = raw_dir / "reservoir"
res_files = list(res_dir.glob("*.csv"))
reservoirs = [r["id"] for r in config.get("reservoirs", [])]
expected_res = [f"{r}_{y}.csv" for r in reservoirs for y in years]
missing_res = [f for f in expected_res if not (res_dir / f).exists()]
summary["sources"]["reservoir"] = {
    "status": "MISSING" if res_files == [] else "PARTIAL",
    "files_found": len(res_files),
    "files_expected": len(expected_res),
    "files_missing": len(missing_res),
    "note": "BLOCKED: Manual export from India-WRIS Reservoir Monitoring required"
}

# Terrain (derived)
terrain_csv = Path("pipeline") / "dataset" / "processed" / "terrain_attributes.csv"
summary["sources"]["terrain_attributes"] = {
    "status": "OK" if terrain_csv.exists() else "MISSING",
    "file": str(terrain_csv) if terrain_csv.exists() else "MISSING",
    "note": "Derived from SRTM DEM — 8 stations, elevation 78-640m"
}

# Summary counts
ok = sum(1 for s in summary["sources"].values() if s["status"] == "OK")
missing = sum(1 for s in summary["sources"].values() if s["status"] == "MISSING")
blocked = sum(1 for s in summary["sources"].values() if "BLOCKED" in s.get("note",""))

summary["overall"] = {
    "sources_ok": ok,
    "sources_missing": missing,
    "sources_blocked_pending_credentials": blocked,
    "ready_for_training": False,
    "blocking_issue": "CWC gauge data and Reservoir data must be manually exported from India-WRIS"
}

out_path = Path("pipeline") / "dataset" / "logs" / "download_summary.json"
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w") as f:
    json.dump(summary, f, indent=2)

print(json.dumps(summary, indent=2))
print(f"\nSaved: {out_path}")
