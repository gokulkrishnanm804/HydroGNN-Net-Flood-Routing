"""
HydroGNN-Net Data Download Orchestrator
========================================
Downloads all official data sources for the Cauvery Basin flood forecasting pipeline.

Usage
-----
    python pipeline/download_all.py                      # Run all sources
    python pipeline/download_all.py --dry-run            # Verify setup only
    python pipeline/download_all.py --source gpm         # Process manual GPM HDF5 files
    python pipeline/download_all.py --source era5        # Download ERA5 only
    python pipeline/download_all.py --source hydrorivers # Download HydroRIVERS
    python pipeline/download_all.py --source srtm        # Download SRTM DEM
    python pipeline/download_all.py --year 2020          # Specific year only
    python pipeline/download_all.py --config path/to/config.yaml

Data Sources
------------
1. NASA GPM IMERG V07    — 30-min precipitation (MANUAL: place HDF5 files in raw/gpm/)
2. ERA5 Copernicus CDS   — Hourly meteorology   (requires CDS API key)
3. HydroRIVERS v1.0      — River network topology (free download)
4. SRTM 30m DEM          — Elevation data (via elevation PyPI)
5. CWC India-WRIS        — River levels (manual CSV export required)
6. CWC Reservoir Data    — Reservoir operations (manual CSV export required)

GPM NOTE
--------
GPM IMERG auto-download is DISABLED. Place manually downloaded HDF5 files
under pipeline/dataset/raw/gpm/{YYYY}/{MM}/ and run --source gpm to process
them into station Parquet files. The ingestor will never delete or modify
your HDF5 files.

IMPORTANT
---------
This script NEVER generates synthetic data. If a data source is unavailable
(missing credentials, missing manual files), it reports the issue clearly
and continues with the remaining sources.

All downloads are cached by MD5 checksum and resume-capable.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

# Ensure pipeline/ is on the Python path
PIPELINE_DIR = Path(__file__).resolve().parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

import yaml

from src.utils.cache import CacheManager, DataSourceUnavailable
from src.utils.logger import DownloadLogger, get_logger, log_separator

logger = get_logger("download_all", log_dir=None)

# ─────────────────────────────────────────────────────────────────────────────


def load_config(config_path: Path) -> dict:
    with open(config_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_dotenv(project_root: Path) -> None:
    """Load .env file from project root into os.environ (if python-dotenv not installed)."""
    env_path = project_root / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv as _ld
        _ld(env_path)
    except ImportError:
        # Minimal .env parser fallback
        with open(env_path) as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())


def print_source_table(results: dict) -> None:
    """Print a formatted summary table of all source download results."""
    print("\n" + "=" * 72)
    print(f"  {'Source':<20} {'Status':<12} {'Notes'}")
    print("=" * 72)
    for src, info in results.items():
        status = info.get("status", "UNKNOWN")
        notes  = info.get("notes", "")
        mark   = "[OK]" if status == "OK" else ("[!!]" if status in ("SKIPPED","DRY-RUN","WARNING") else "[--]")
        print(f"  {mark} {src:<19} {status:<12} {notes}")
    print("=" * 72 + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Source handlers
# ─────────────────────────────────────────────────────────────────────────────

def handle_hydrorivers(config: dict, cache: CacheManager,
                        dl_log: DownloadLogger, dry_run: bool) -> dict:
    """Download and clip HydroRIVERS shapefile."""
    from src.downloaders.hydrorivers import HydroRIVERSDownloader
    d = HydroRIVERSDownloader(cache, dl_log, config)
    raw_dir = Path(config["paths"]["raw_dir"]) / "hydrorivers"
    src_url = getattr(d, "URL", getattr(d, "BASE_URL", config.get("hydrorivers", {}).get("url", "?")))
    if dry_run:
        return {"status": "DRY-RUN", "notes": f"Would download: {src_url}"}
    try:
        shp = d.download_hydrorivers(raw_dir)
        bbox_shp = d.clip_to_basin(shp, config["basin"]["bbox"],
                                   raw_dir / "cauvery_rivers.shp")
        # clip_to_basin may return a GeoDataFrame or a Path; handle both
        try:
            seg_count = len(bbox_shp)
            notes = f"{seg_count} river segments clipped"
        except TypeError:
            notes = f"Clipped shapefile: {bbox_shp}"
        return {"status": "OK", "notes": notes}
    except Exception as e:
        return {"status": "FAILED", "notes": str(e)[:120]}


def handle_srtm(config: dict, cache: CacheManager,
                dl_log: DownloadLogger, dry_run: bool) -> dict:
    """Download SRTM DEM and compute terrain attributes."""
    from src.downloaders.srtm import SRTMDownloader
    d = SRTMDownloader(config, cache, dl_log)
    raw_dir  = Path(config["paths"]["raw_dir"]) / "srtm"
    raw_dir.mkdir(parents=True, exist_ok=True)
    dem_path = raw_dir / "cauvery_dem.tif"
    if dry_run:
        return {"status": "DRY-RUN", "notes": "Would download SRTM1 tiles via elevation PyPI"}
    try:
        d.download_basin_dem(config["basin"]["bbox"], dem_path)
        proc_dir = Path(config["paths"]["processed_dir"])
        d.compute_terrain_attributes(dem_path, proc_dir)
        return {"status": "OK", "notes": f"DEM at {dem_path}"}
    except DataSourceUnavailable as e:
        return {"status": "FAILED", "notes": str(e)[:120]}
    except Exception as e:
        return {"status": "FAILED", "notes": str(e)[:80]}


def handle_era5(config: dict, cache: CacheManager, dl_log: DownloadLogger,
                dry_run: bool, years: list) -> dict:
    """Download ERA5 reanalysis month-by-month (avoids CDS cost-limit 403 errors)."""
    from src.downloaders.era5 import ERA5Downloader
    try:
        d = ERA5Downloader(cache, dl_log, config)
    except DataSourceUnavailable as e:
        return {"status": "FAILED", "notes": str(e)[:160]}

    raw_dir  = Path(config["paths"]["raw_dir"]) / "era5"
    proc_dir = Path(config["paths"]["processed_dir"])
    proc_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    station_ids    = [s["id"]            for s in config["stations"]]
    station_coords = [(s["lat"], s["lon"]) for s in config["stations"]]

    if dry_run:
        total_months = len(years) * 12
        return {"status": "DRY-RUN",
                "notes": f"Would submit {total_months} monthly CDS requests ({len(years)} years)"}

    ok_months, fail_months = [], []

    for yr in years:
        for mo in range(1, 13):
            nc_path = raw_dir / f"era5_{yr}_{mo:02d}.nc"
            label   = f"{yr}-{mo:02d}"
            try:
                d.download_month(yr, mo, nc_path)
                df_month = d.extract_station_values(nc_path, station_ids, station_coords)

                # Save per-station records immediately for this month
                if not df_month.empty and "station_id" in df_month.columns:
                    for sid, grp in df_month.groupby("station_id"):
                        df_month_station = grp.drop(columns=["station_id"])
                        out = proc_dir / f"era5_{sid}.parquet"
                        if out.exists():
                            existing = pd.read_parquet(out)
                            df_month_station = pd.concat([existing, df_month_station], ignore_index=True)
                            ts_col = "timestamp" if "timestamp" in df_month_station.columns else df_month_station.index.name
                            if ts_col and ts_col in df_month_station.columns:
                                df_month_station = (
                                    df_month_station
                                    .drop_duplicates(subset=[ts_col])
                                    .sort_values(ts_col)
                                    .reset_index(drop=True)
                                )
                        df_month_station.to_parquet(out, index=False)

                # Delete monthly NetCDF to save disk (~20-50 MB per month)
                if nc_path.exists():
                    nc_path.unlink()
                    logger.debug(f"ERA5 {label}: deleted NetCDF after extraction")

                ok_months.append(label)
                logger.info(f"ERA5 {label}: extracted {len(df_month):,} rows, NetCDF deleted")

            except Exception as e:
                logger.error(f"ERA5 {label}: {e}")
                fail_months.append(label)
                # Don't delete on failure — allow manual retry
                continue

        logger.info(f"ERA5 year {yr} completed processing")

    ok_years  = sorted({m[:4] for m in ok_months})
    fail_years = sorted({m[:4] for m in fail_months} - {m[:4] for m in ok_months})
    status = "OK" if ok_months and not fail_years else ("WARNING" if ok_months else "FAILED")
    notes  = (f"Years OK: {ok_years}"
              + (f" | Months failed: {fail_months}" if fail_months else ""))
    return {"status": status, "notes": notes}



def handle_gpm(config: dict, cache: CacheManager, dl_log: DownloadLogger,
               dry_run: bool, years: list) -> dict:
    """
    Process manually downloaded GPM IMERG HDF5 files.

    Auto-download is DISABLED. This function scans raw/gpm/ for HDF5 files
    already placed by the user, validates each one, extracts station
    precipitation values, and writes station-specific Parquet files.

    No network I/O. No NASA credentials required. Original HDF5 files are
    never deleted or modified.
    """
    from src.downloaders.gpm_manual_ingest import GPMManualIngestor

    station_ids    = [s["id"]            for s in config["stations"]]
    station_coords = [(s["lat"], s["lon"]) for s in config["stations"]]
    raw_gpm_dir    = Path(config["paths"]["raw_dir"]) / "gpm"

    if dry_run:
        hdf5_files = list(raw_gpm_dir.rglob("*.HDF5")) + list(raw_gpm_dir.rglob("*.hdf5"))
        return {
            "status": "DRY-RUN",
            "notes": (
                f"Manual mode: found {len(hdf5_files)} HDF5 file(s) in {raw_gpm_dir}. "
                f"Run without --dry-run to validate and extract to Parquet."
            ),
        }

    try:
        ingestor = GPMManualIngestor(cache, dl_log, config)
        report   = ingestor.run(station_ids, station_coords)
    except Exception as e:
        logger.error(f"GPM manual ingest error: {e}")
        return {"status": "FAILED", "notes": str(e)[:200]}

    n_proc  = report.get("processed", 0)
    n_skip  = report.get("skipped_existing", 0)
    n_fail  = report.get("failed", 0)
    n_found = report.get("hdf5_found", 0)
    cov_s   = report.get("coverage_start", "N/A")
    cov_e   = report.get("coverage_end",   "N/A")

    if n_found == 0:
        return {
            "status": "SKIPPED",
            "notes": (
                f"No HDF5 files found in {raw_gpm_dir}. "
                "Download GPM IMERG files manually and place them under "
                "pipeline/dataset/raw/gpm/{YYYY}/{MM}/"
            ),
        }

    status = "OK" if n_fail == 0 else ("WARNING" if n_proc > 0 else "FAILED")
    notes  = (
        f"Found={n_found} | Processed={n_proc} | "
        f"Skipped={n_skip} | Failed={n_fail} | "
        f"Coverage: {cov_s} → {cov_e}"
    )
    return {"status": status, "notes": notes}


def handle_cwc(config: dict, dry_run: bool) -> dict:
    """Check and parse CWC gauge data (manual CSV files)."""
    from src.downloaders.cwc import CWCDataParser
    raw_dir = Path(config["paths"]["raw_dir"])
    d = CWCDataParser(raw_dir, config)
    station_ids = [s["id"] for s in config["stations"]]
    available   = d.check_data_availability()
    missing     = d.report_missing_stations(available, station_ids)

    if dry_run:
        found = list(available.keys())
        return {
            "status": "DRY-RUN",
            "notes": (
                f"Found CSV data for: {found}. "
                f"Missing: {missing}. "
                f"Place files in dataset/raw/cwc/{{station_id}}_{{YYYY}}.csv"
            ),
        }

    if not available:
        return {
            "status": "SKIPPED",
            "notes": (
                "No CWC CSV files found in dataset/raw/cwc/. "
                "Export from https://indiawris.gov.in/wris/ and place files as "
                "dataset/raw/cwc/{STATION_ID}_{YYYY}.csv"
            ),
        }

    proc_dir = Path(config["paths"]["processed_dir"])
    years = list(range(config["years"]["start"], config["years"]["end"] + 1))
    data = d.load_all_available(station_ids, years)
    d.save_processed(data, proc_dir)
    return {"status": "OK",
            "notes": f"Parsed {len(data)} stations. Missing: {missing}"}


def handle_reservoir(config: dict, dry_run: bool) -> dict:
    """Check and parse reservoir data (manual CSV files)."""
    from src.downloaders.reservoir import ReservoirDataParser
    raw_dir = Path(config["paths"]["raw_dir"])
    d = ReservoirDataParser(raw_dir, config)
    res_ids   = [r["id"] for r in config["reservoirs"]]
    available = d.check_data_availability()
    missing   = d.report_missing_reservoirs(available, res_ids)

    if dry_run:
        return {
            "status": "DRY-RUN",
            "notes": (
                f"Found: {list(available.keys())}. "
                f"Missing: {missing}. "
                f"Place files in dataset/raw/reservoir/{{RESERVOIR_ID}}_{{YYYY}}.csv"
            ),
        }

    if not available:
        return {
            "status": "SKIPPED",
            "notes": "No reservoir CSV files found. Export from India-WRIS.",
        }

    proc_dir = Path(config["paths"]["processed_dir"])
    years = list(range(config["years"]["start"], config["years"]["end"] + 1))
    data = d.load_all_available(res_ids, years)
    d.save_processed(data, proc_dir)
    return {"status": "OK",
            "notes": f"Parsed {len(data)} reservoirs. Missing: {missing}"}


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="HydroGNN-Net Data Download Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--config",   default="pipeline/config.yaml",
                        help="Path to config.yaml (default: pipeline/config.yaml)")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Verify credentials and list files without downloading")
    parser.add_argument("--source",   choices=["gpm", "era5", "hydrorivers", "srtm", "cwc", "reservoir"],
                        help="Download only a specific source")
    parser.add_argument("--year",     type=int,
                        help="Download only a specific year (overrides config year range)")
    args = parser.parse_args()

    # ── Locate project root and load config ───────────────────────────────
    project_root = PIPELINE_DIR.parent
    load_dotenv(project_root)

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = project_root / config_path
    if not config_path.exists():
        logger.error(f"Config not found: {config_path}")
        sys.exit(1)

    config = load_config(config_path)

    # Resolve paths relative to project root
    for key in config["paths"]:
        p = Path(config["paths"][key])
        if not p.is_absolute():
            config["paths"][key] = str(project_root / "pipeline" / p)

    # ── Year range ────────────────────────────────────────────────────────
    if args.year:
        years = [args.year]
    else:
        start = config["years"]["start"]
        end   = config["years"]["end"]
        years = list(range(start, end + 1))

    # ── Setup cache and download logger ───────────────────────────────────
    logs_dir = Path(config["paths"]["logs_dir"])
    logs_dir.mkdir(parents=True, exist_ok=True)
    cache  = CacheManager(logs_dir / "cache")
    dl_log = DownloadLogger(logs_dir / "download_log.csv")

    # ── Run downloads ─────────────────────────────────────────────────────
    log_separator(logger, f"HydroGNN-Net Data Download  {'[DRY RUN]' if args.dry_run else ''}")
    logger.info(f"Basin: {config['basin']['name']}  |  Years: {years[0]}–{years[-1]}")
    logger.info(f"Config: {config_path}")

    ALL_SOURCES = ["hydrorivers", "srtm", "era5", "gpm", "cwc", "reservoir"]
    sources = [args.source] if args.source else ALL_SOURCES

    results: dict = {}

    for src in sources:
        log_separator(logger, f"Source: {src.upper()}")
        if src == "hydrorivers":
            results[src] = handle_hydrorivers(config, cache, dl_log, args.dry_run)
        elif src == "srtm":
            results[src] = handle_srtm(config, cache, dl_log, args.dry_run)
        elif src == "era5":
            results[src] = handle_era5(config, cache, dl_log, args.dry_run, years)
        elif src == "gpm":
            results[src] = handle_gpm(config, cache, dl_log, args.dry_run, years)
        elif src == "cwc":
            results[src] = handle_cwc(config, args.dry_run)
        elif src == "reservoir":
            results[src] = handle_reservoir(config, args.dry_run)

        status = results[src].get("status", "?")
        logger.info(f"{src}: {status} — {results[src].get('notes', '')[:100]}")

    print_source_table(results)

    dl_stats = dl_log.get_summary()
    logger.info(
        f"Download summary: {dl_stats['success']} OK, "
        f"{dl_stats['failed']} failed, {dl_stats['skipped']} skipped, "
        f"{dl_stats['total_bytes'] / 1e9:.2f} GB total"
    )


if __name__ == "__main__":
    main()
