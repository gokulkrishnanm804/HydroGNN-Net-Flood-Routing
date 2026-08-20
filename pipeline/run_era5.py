"""
ERA5 Standalone Downloader
===========================
Downloads the complete ERA5 dataset for the Cauvery Basin (2018-2023)
without running any other pipeline components.

Usage
-----
    python pipeline/run_era5.py                # Download all 6 years
    python pipeline/run_era5.py --year 2020    # Download a single year
    python pipeline/run_era5.py --dry-run      # Check setup, no download
    python pipeline/run_era5.py --config path/to/config.yaml

What this does
--------------
1. Downloads ERA5 hourly reanalysis month-by-month (72 CDS requests for 6 years).
   Each request covers 1 month, all configured variables, Cauvery basin bbox.
2. Validates each downloaded NetCDF file before extraction.
3. Extracts station-level values (nearest grid-point) for all 8 stations.
4. Writes per-station Parquet files to pipeline/dataset/processed/era5_{ID}.parquet
5. Resumes automatically — already-downloaded months are skipped.
6. Writes a JSON progress/coverage report to pipeline/dataset/logs/era5_coverage_report.json

Variables downloaded
--------------------
    t2m    : 2m air temperature          [K → °C after extraction]
    d2m    : 2m dewpoint temperature     [K → °C]
    u10    : 10m eastward wind component [m/s]
    v10    : 10m northward wind component[m/s]
    sp     : Surface pressure            [Pa]
    swvl1  : Volumetric soil water L1   [m³/m³]
    e      : Evaporation                 [m/h → mm after extraction]

Credentials
-----------
Requires ~/.cdsapirc with:
    url: https://cds.climate.copernicus.eu/api
    key: <your-api-key>

Reference
---------
    Hersbach, H. et al. (2020). The ERA5 global reanalysis.
    Quarterly Journal of the Royal Meteorological Society, 146(730), 1999-2049.
    https://doi.org/10.1002/qj.3803
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

# ── Ensure pipeline/ is on sys.path ──────────────────────────────────────────
PIPELINE_DIR = Path(__file__).resolve().parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

import yaml

from src.utils.cache import CacheManager, DataSourceUnavailable
from src.utils.logger import DownloadLogger, get_logger, log_separator

logger = get_logger("run_era5", log_dir=None)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_config(config_path: Path) -> dict:
    with open(config_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_dotenv(project_root: Path) -> None:
    """Load .env from project root into os.environ."""
    import os
    env_path = project_root / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv as _ld
        _ld(env_path)
    except ImportError:
        with open(env_path) as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())


def _validate_netcdf(nc_path: Path, expected_vars: list) -> tuple[bool, str]:
    """Validate a downloaded NetCDF file before extraction."""
    import xarray as xr
    try:
        ds = xr.open_dataset(nc_path, engine="netcdf4")
        all_vars = list(ds.data_vars) + list(ds.coords)
        ds.close()
        missing = [v for v in expected_vars if v not in all_vars]
        if missing:
            return False, f"Missing variables: {missing}"
        return True, ""
    except Exception as e:
        return False, str(e)


# ─────────────────────────────────────────────────────────────────────────────
# ERA5 runner
# ─────────────────────────────────────────────────────────────────────────────

def run_era5(
    config: dict,
    years: list,
    dry_run: bool,
    logs_dir: Path,
    cache: CacheManager,
    dl_log: DownloadLogger,
) -> dict:
    """
    Download and process ERA5 data using moderate parallelism.
    """
    from src.downloaders.era5 import ERA5ParallelDownloader

    try:
        downloader = ERA5ParallelDownloader(cache, dl_log, config)
    except DataSourceUnavailable as e:
        logger.error(f"ERA5 environment check failed: {e}")
        return {"status": "FAILED", "notes": str(e)[:300]}

    station_ids    = [s["id"]             for s in config["stations"]]
    station_coords = [(s["lat"], s["lon"]) for s in config["stations"]]

    # Run parallel downloader
    result = downloader.run_parallel(
        years=years,
        station_ids=station_ids,
        station_coords=station_coords,
        dry_run=dry_run,
    )

    # Write a JSON progress/coverage report
    if not dry_run:
        # Build per-station row counts from Parquet
        station_coverage = {}
        for sid in station_ids:
            p = Path(config["paths"]["processed_dir"]) / f"era5_{sid}.parquet"
            if p.exists():
                try:
                    df = pd.read_parquet(p, columns=["timestamp"])
                    ts = pd.to_datetime(df["timestamp"], utc=True)
                    station_coverage[sid] = {
                        "rows":        len(df),
                        "start":       str(ts.min()),
                        "end":         str(ts.max()),
                        "size_kb":     round(p.stat().st_size / 1024, 1),
                    }
                except Exception:
                    station_coverage[sid] = {"rows": "error reading Parquet"}

        coverage_report = {
            "generated_at":     pd.Timestamp.now("UTC").isoformat(),
            "years_requested":  years,
            "total_months":     len(years) * 12,
            "station_coverage": station_coverage,
            "status":           result.get("status", "UNKNOWN"),
            "notes":            result.get("notes", ""),
        }

        report_path = logs_dir / "era5_coverage_report.json"
        try:
            report_path.write_text(json.dumps(coverage_report, indent=2, default=str))
            logger.info(f"ERA5 coverage report → {report_path}")
        except Exception as e:
            logger.warning(f"Could not write ERA5 coverage report: {e}")
            
        result["coverage_report_path"] = str(report_path)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ERA5 Standalone Downloader — Cauvery Basin (2018-2023)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config", default="pipeline/config.yaml",
        help="Path to config.yaml (default: pipeline/config.yaml)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Check setup and list what would be downloaded without making requests",
    )
    parser.add_argument(
        "--year", type=int,
        help="Download only a single year (overrides config year range)",
    )
    args = parser.parse_args()

    # ── Load config ───────────────────────────────────────────────────────────
    project_root = PIPELINE_DIR.parent
    load_dotenv(project_root)

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = project_root / config_path
    if not config_path.exists():
        logger.error(f"Config not found: {config_path}")
        sys.exit(1)

    config = load_config(config_path)

    # Resolve relative paths
    for key in config["paths"]:
        p = Path(config["paths"][key])
        if not p.is_absolute():
            config["paths"][key] = str(project_root / "pipeline" / p)

    # ── Year range ────────────────────────────────────────────────────────────
    if args.year:
        years = [args.year]
        logger.info(f"ERA5: single-year mode — {args.year}")
    else:
        start = config["years"]["start"]
        end   = config["years"]["end"]
        years = list(range(start, end + 1))
        logger.info(f"ERA5: full range — {start}–{end} ({len(years)} years)")

    # ── Setup infra ───────────────────────────────────────────────────────────
    logs_dir = Path(config["paths"]["logs_dir"])
    logs_dir.mkdir(parents=True, exist_ok=True)
    cache  = CacheManager(logs_dir / "cache")
    dl_log = DownloadLogger(logs_dir / "download_log.csv")

    # ── Run ───────────────────────────────────────────────────────────────────
    result = run_era5(
        config=config,
        years=years,
        dry_run=args.dry_run,
        logs_dir=logs_dir,
        cache=cache,
        dl_log=dl_log,
    )

    status = result.get("status", "UNKNOWN")
    if status == "FAILED":
        sys.exit(1)
    elif status == "WARNING":
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
