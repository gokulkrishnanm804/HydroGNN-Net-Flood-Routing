"""
Copernicus ERA5 Reanalysis Downloader

Downloads ERA5 hourly reanalysis on single levels for the basin bounding box.
Requires a Copernicus CDS account and ~/.cdsapirc API key file.

Registration (free): https://cds.climate.copernicus.eu
After registration, create ~/.cdsapirc with:
    url: https://cds.climate.copernicus.eu/api
    key: <your-uid>:<your-api-key>

Reference:
    Hersbach, H. et al. (2020). The ERA5 global reanalysis.
    Quarterly Journal of the Royal Meteorological Society, 146(730), 1999-2049.
    https://doi.org/10.1002/qj.3803
"""
from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.downloaders.base import BaseDownloader
from src.utils.cache import CacheManager, DataSourceUnavailable
from src.utils.logger import DownloadLogger, get_logger

logger = get_logger(__name__)


class ERA5Downloader(BaseDownloader):
    """
    Downloads ERA5 hourly reanalysis data using the Copernicus CDS API.

    Uses cdsapi.Client().retrieve() to fetch NetCDF files for each year.
    Station values are extracted by nearest-grid-point selection using xarray.
    """

    SOURCE = "ERA5_CDS"

    def __init__(
        self,
        cache_manager: CacheManager,
        download_logger: DownloadLogger,
        config: dict,
    ) -> None:
        super().__init__(cache_manager, download_logger, config)
        self.bbox      = config["basin"]["bbox"]   # [lon_min, lat_min, lon_max, lat_max]
        self.variables = config["era5"]["variables"]
        self.grid      = config["era5"].get("grid_resolution", 0.25)
        self.raw_dir   = Path(config["paths"]["raw_dir"]) / "era5"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self._check_environment()

    # ------------------------------------------------------------------ #
    # Environment checks
    # ------------------------------------------------------------------ #

    def _check_environment(self) -> None:
        """Raise DataSourceUnavailable if cdsapi or ~/.cdsapirc are missing."""
        try:
            import cdsapi  # noqa: F401
        except ImportError:
            raise DataSourceUnavailable(
                "The 'cdsapi' package is not installed.\n"
                "\n"
                "  Install it:\n"
                "      pip install cdsapi\n"
                "\n"
                "  Then register at: https://cds.climate.copernicus.eu\n"
                "  And create ~/.cdsapirc:\n"
                "      url: https://cds.climate.copernicus.eu/api\n"
                "      key: <uid>:<api-key>\n"
            )

        cds_rc = Path(os.path.expanduser("~/.cdsapirc"))
        if not cds_rc.exists():
            raise DataSourceUnavailable(
                "Copernicus CDS API key file not found: ~/.cdsapirc\n"
                "\n"
                "  Steps:\n"
                "  1. Register at https://cds.climate.copernicus.eu (free)\n"
                "  2. Accept the ERA5 Terms of Use on the dataset page\n"
                "  3. Create ~/.cdsapirc with:\n"
                "         url: https://cds.climate.copernicus.eu/api\n"
                "         key: <your-uid>:<your-api-key>\n"
                "  (Your UID and API key appear on your CDS profile page)\n"
            )

    # ------------------------------------------------------------------ #
    # Download
    # ------------------------------------------------------------------ #

    def download_month(
        self,
        year: int,
        month: int,
        output_path: Path,
    ) -> Path:
        """
        Download ERA5 data for a single calendar month.

        CDS rejects full-year requests (403 cost limits exceeded) for
        multi-variable, hourly, bbox requests. Monthly chunks are well
        within the CDS cost budget and are the recommended approach.

        Parameters
        ----------
        year        : Calendar year (e.g. 2020).
        month       : Month number 1-12.
        output_path : Destination .nc file path.

        Returns
        -------
        Path to the downloaded NetCDF file.
        """
        import cdsapi, calendar

        output_path = Path(output_path)
        if self.skip_if_exists(output_path):
            logger.info(f"ERA5 {year}-{month:02d}: already exists, skipping")
            return output_path

        lon_min, lat_min, lon_max, lat_max = self.bbox
        area = [lat_max, lon_min, lat_min, lon_max]  # CDS: [N, W, S, E]

        # Days in this month (handles leap years)
        _, n_days = calendar.monthrange(year, month)

        request = {
            "product_type": "reanalysis",
            "variable":     self.variables,
            "year":         str(year),
            "month":        f"{month:02d}",
            "day":          [f"{d:02d}" for d in range(1, n_days + 1)],
            "time":         [f"{h:02d}:00" for h in range(24)],
            "area":         area,
            "grid":         [self.grid, self.grid],
            "data_format":      "netcdf",       # CDS API v2: 'format' -> 'data_format'
            "download_format":  "unarchived",   # CDS API v2: return raw .nc, not .zip
        }

        logger.info(f"ERA5 {year}-{month:02d}: submitting CDS request...")
        client = cdsapi.Client(quiet=True)
        client.retrieve(
            "reanalysis-era5-single-levels",
            request,
            str(output_path),
        )
        size_mb = output_path.stat().st_size / 1e6
        logger.info(f"ERA5 {year}-{month:02d}: downloaded {size_mb:.0f} MB -> {output_path.name}")
        return output_path

    # ------------------------------------------------------------------ #
    # Extraction
    # ------------------------------------------------------------------ #

    def extract_station_values(
        self,
        nc_path: Path,
        station_ids: List[str],
        station_coords: List[Tuple[float, float]],
    ) -> pd.DataFrame:
        """
        Extract meteorological variables at each station using nearest grid point.

        Derived variables:
        - temperature_c  : 2m air temperature [°C]
        - humidity_pct   : Relative humidity [%] via Magnus formula
        - wind_speed_ms  : 10m wind speed [m/s]
        - pressure_pa    : Surface pressure [Pa]
        - evaporation_mm : Evaporation [mm] (ERA5 unit: m, sign convention: negative = upward)
        - soil_moisture  : Volumetric soil water layer 1 [m³/m³]

        Resampled to 30-minute resolution by linear interpolation.

        Parameters
        ----------
        nc_path        : Path to ERA5 NetCDF file.
        station_ids    : List of station ID strings.
        station_coords : List of (lat, lon) tuples.

        Returns
        -------
        pd.DataFrame with UTC DatetimeIndex (30T) and columns:
            [station_id, temperature_c, humidity_pct, wind_speed_ms,
             pressure_pa, evaporation_mm, soil_moisture]
        """
        import xarray as xr
        import zipfile
        import shutil
        import tempfile

        # Check if the downloaded file is a ZIP archive (CDS API v2 default)
        is_zip = zipfile.is_zipfile(nc_path)
        temp_dir = None
        datasets = []
        
        if is_zip:
            temp_dir = Path(tempfile.mkdtemp(prefix="era5_extracted_"))
            with zipfile.ZipFile(nc_path, "r") as z:
                z.extractall(temp_dir)
            nc_files = list(temp_dir.glob("*.nc"))
            if not nc_files:
                raise ValueError(f"No NetCDF files found in the extracted archive from {nc_path}")
            # Open and merge all NetCDF files
            for f in nc_files:
                datasets.append(xr.open_dataset(f))
            ds = xr.merge(datasets)
        else:
            ds = xr.open_dataset(nc_path)

        try:
            # Rename coordinate 'valid_time' to 'time' if present (CDS API v2 convention)
            if "valid_time" in ds.coords and "time" not in ds.coords:
                ds = ds.rename({"valid_time": "time"})

            # Rename ERA5 coordinate variants
            rename_map = {}
            if "latitude" not in ds.coords and "lat" in ds.coords:
                rename_map["lat"] = "latitude"
            if "longitude" not in ds.coords and "lon" in ds.coords:
                rename_map["lon"] = "longitude"
            if rename_map:
                ds = ds.rename(rename_map)

            records = []
            for sid, (slat, slon) in zip(station_ids, station_coords):
                try:
                    pt = ds.sel(latitude=slat, longitude=slon, method="nearest")
                except Exception as exc:
                    logger.warning(f"ERA5 extraction failed for {sid}: {exc}")
                    continue

                # Temperature (K → °C)
                t2m  = pt["t2m"].values - 273.15 if "t2m" in pt else np.full(len(pt.time), np.nan)
                if "d2m" in pt:
                    d2m = pt["d2m"].values - 273.15
                else:
                    d2m = t2m - 2.0   # rough approximation: dew point ≈ T - 2°C
                    logger.warning(
                        f"ERA5 station {sid}: 'd2m' (dew point) not in dataset. "
                        "Falling back to T2m - 2°C for relative humidity calculation."
                    )

                # Relative humidity via Magnus formula (moved outside loop for efficiency)
                # RH = 100 * exp(17.625*Td/(243.04+Td)) / exp(17.625*T/(243.04+T))
                def _magnus(T):  # noqa: E306 (defined once per station iteration, not per call)
                    return np.exp(17.625 * T / (243.04 + T))
                rh = np.clip(100.0 * _magnus(d2m) / np.maximum(_magnus(t2m), 1e-9), 0, 100)

                # Wind speed (m/s)
                u10 = pt["u10"].values if "u10" in pt else np.zeros(len(pt.time))
                v10 = pt["v10"].values if "v10" in pt else np.zeros(len(pt.time))
                ws  = np.sqrt(u10 ** 2 + v10 ** 2)

                # Surface pressure (Pa)
                sp = pt["sp"].values if "sp" in pt else np.full(len(pt.time), 101325.0)

                # Evaporation (m → mm, ERA5 convention: negative = upward evaporation)
                e_raw = pt["e"].values if "e" in pt else np.zeros(len(pt.time))
                evap_mm = -e_raw * 1000.0  # positive = water leaves surface

                # Soil moisture volumetric layer 1 (already in m³/m³)
                swvl1 = pt["swvl1"].values if "swvl1" in pt else np.full(len(pt.time), np.nan)

                # Build hourly series
                times = pd.to_datetime(pt["time"].values, utc=True)
                df_hourly = pd.DataFrame({
                    "timestamp":       times,
                    "temperature_c":   t2m,
                    "humidity_pct":    rh,
                    "wind_speed_ms":   ws,
                    "pressure_pa":     sp,
                    "evaporation_mm":  evap_mm,
                    "soil_moisture":   swvl1,
                }).set_index("timestamp")

                # Resample to 30-minute grid via linear interpolation
                # Note: '30T' is deprecated in pandas >= 2.2; use '30min'
                df_30 = df_hourly.resample("30min").interpolate("linear")
                df_30["station_id"] = sid
                records.append(df_30.reset_index())

        finally:
            # Safely close all opened Datasets to release Windows file locks
            ds.close()
            for dataset in datasets:
                dataset.close()
            # Clean up temp folder
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

        if not records:
            return pd.DataFrame()

        return pd.concat(records, ignore_index=True)

    # ------------------------------------------------------------------ #
    # Save
    # ------------------------------------------------------------------ #

    def save_station_extracts(
        self,
        df: pd.DataFrame,
        output_dir: Path,
    ) -> None:
        """Save per-station ERA5 extracts as Parquet files."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        for sid, grp in df.groupby("station_id"):
            out = output_dir / f"era5_{sid}.parquet"
            grp.drop(columns=["station_id"]).to_parquet(out, index=False)
            logger.debug(f"Saved ERA5 extract: {out.name} ({len(grp):,} rows)")

    def load_all_years(
        self,
        years: List[int],
        processed_dir: Path,
    ) -> Dict[str, pd.DataFrame]:
        """Load per-station parquet files from *processed_dir* for the given years."""
        result: Dict[str, pd.DataFrame] = {}
        year_set = {str(y) for y in years} if years else None
        for p in Path(processed_dir).glob("era5_*.parquet"):
            sid = p.stem.replace("era5_", "")
            df  = pd.read_parquet(p)
            # Filter to requested years if a years list was provided
            if year_set and "timestamp" in df.columns:
                ts_col = pd.to_datetime(df["timestamp"], utc=True)
                df = df[ts_col.dt.year.astype(str).isin(year_set)]
            elif year_set and df.index.dtype == "datetime64[ns, UTC]":
                df = df[df.index.year.astype(str).isin(year_set)]
            result[sid] = df
        logger.info(f"Loaded ERA5 for {len(result)} stations (years={years})")
        return result


# ═══════════════════════════════════════════════════════════════════════════
# Parallel Downloader & Extractor
# ═══════════════════════════════════════════════════════════════════════════

class ERA5ParallelDownloader(ERA5Downloader):
    """
    High-performance ERA5 downloader with moderate parallelism.
    Uses 2 concurrent download threads and 1 parallel extraction/writing consumer.
    """

    def __init__(
        self,
        cache_manager: CacheManager,
        download_logger: DownloadLogger,
        config: dict,
    ) -> None:
        super().__init__(cache_manager, download_logger, config)
        self.max_workers = 2
        self.proc_dir = Path(config["paths"]["processed_dir"])
        self.proc_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def _get_completed_months(self, station_ids: List[str]) -> set[tuple[int, int]]:
        """Determine which months have already been fully processed by reading the reference parquet."""
        completed = set()
        ref_parq = self.proc_dir / f"era5_{station_ids[0]}.parquet"
        if ref_parq.exists():
            try:
                existing_df = pd.read_parquet(ref_parq, columns=["timestamp"])
                existing_ts = pd.to_datetime(existing_df["timestamp"], utc=True)
                import calendar
                for (yr, mo), grp in existing_ts.groupby([existing_ts.dt.year, existing_ts.dt.month]):
                    _, days = calendar.monthrange(yr, mo)
                    expected_rows = days * 48
                    if len(grp) >= expected_rows - 2:
                        completed.add((yr, mo))
            except Exception as e:
                logger.warning(f"Could not check existing Parquet state: {e}")
        return completed

    def validate_parquets(self, station_ids: List[str]) -> bool:
        """
        Validate that the final Parquet files are correctly structured, sorted,
        and identical in format to the sequential implementation.
        """
        logger.info("Validating Parquet outputs...")
        expected_columns = [
            "temperature_c", "humidity_pct", "wind_speed_ms",
            "pressure_pa", "evaporation_mm", "soil_moisture"
        ]
        all_ok = True
        for sid in station_ids:
            p = self.proc_dir / f"era5_{sid}.parquet"
            if not p.exists():
                logger.error(f"Validation failed: output Parquet missing for {sid}")
                all_ok = False
                continue
            try:
                df = pd.read_parquet(p)
                # Check columns
                missing_cols = [c for c in expected_columns if c not in df.columns]
                if missing_cols:
                    logger.error(f"Validation failed for {sid}: missing columns {missing_cols}")
                    all_ok = False
                # Check timestamp
                if "timestamp" not in df.columns:
                    logger.error(f"Validation failed for {sid}: missing 'timestamp' column")
                    all_ok = False
                else:
                    ts = pd.to_datetime(df["timestamp"])
                    if not ts.is_monotonic_increasing:
                        logger.error(f"Validation failed for {sid}: timestamps are not sorted")
                        all_ok = False
                    if ts.duplicated().any():
                        logger.error(f"Validation failed for {sid}: duplicate timestamps found")
                        all_ok = False
                logger.info(f"Validation passed for {sid} ({len(df):,} rows)")
            except Exception as e:
                logger.error(f"Validation error reading Parquet for {sid}: {e}")
                all_ok = False
        return all_ok

    def run_parallel(
        self,
        years: List[int],
        station_ids: List[str],
        station_coords: List[Tuple[float, float]],
        dry_run: bool = False,
    ) -> dict:
        """
        Execute concurrent downloading and extraction.
        Downloads at most 2 months in parallel; extracts and writes to Parquet in the background.
        """
        import queue

        # Build list of all requested months
        all_months = []
        for yr in years:
            for mo in range(1, 13):
                all_months.append((yr, mo))

        # Filter out completed months (resume capability)
        completed = self._get_completed_months(station_ids)
        to_process = [m for m in all_months if m not in completed]

        logger.info(f"ERA5 Concurrency check: {len(all_months)} total months requested. "
                    f"{len(completed)} already completed. {len(to_process)} remaining.")

        if dry_run:
            print("\n" + "=" * 60)
            print("  ERA5 Parallel Dry-Run Summary")
            print("=" * 60)
            print(f"  Total requested : {len(all_months)} months")
            print(f"  Already done    : {len(completed)} months")
            print(f"  To download     : {len(to_process)} months")
            print("=" * 60 + "\n")
            return {"status": "DRY-RUN", "notes": f"{len(to_process)} months remaining"}

        if not to_process:
            logger.info("All months already complete. Nothing to do!")
            self.validate_parquets(station_ids)
            return {"status": "OK", "notes": "All months already complete."}

        # Shared queue and sync locks
        processing_queue = queue.Queue()
        active_downloads = {}
        ok_months = []
        fail_months = []
        start_time = time.monotonic()
        total_to_download = len(to_process)
        SENTINEL = object()

        # Helper to print the progress table
        def print_progress():
            with self.lock:
                active_list = []
                now = time.monotonic()
                for lbl, t_start in list(active_downloads.items()):
                    elapsed = now - t_start
                    active_list.append(f"{lbl} ({elapsed:.0f}s)")
                active_str = ", ".join(active_list) if active_list else "None"

                done = len(ok_months)
                failed = len(fail_months)
                total_completed = done + failed
                remaining = total_to_download - total_completed
                elapsed_total = now - start_time

                # Month size average ~3.6 MB
                total_est_bytes = done * 3.6 * 1024 * 1024
                speed_mbs = (total_est_bytes / elapsed_total) / (1024 * 1024) if elapsed_total > 0 else 0.0

                avg_time_per_month = elapsed_total / total_completed if total_completed > 0 else 0.0
                eta_seconds = remaining * avg_time_per_month if avg_time_per_month > 0 else 0.0

                if eta_seconds > 0:
                    eta_min = int(eta_seconds // 60)
                    eta_sec = int(eta_seconds % 60)
                    eta_str = f"{eta_min}m {eta_sec}s"
                else:
                    eta_str = "Calculating..."

                pct = (total_completed / total_to_download * 100) if total_to_download > 0 else 100.0

                print("\n" + "=" * 68)
                print("  ERA5 Parallel Downloader Progress")
                print("=" * 68)
                print(f"  Active Downloads : {active_str}")
                print(f"  Current Progress : {done} / {total_to_download} completed ({pct:.1f}%)")
                print(f"  Failed Months    : {failed}")
                print(f"  Remaining Months : {remaining}")
                print(f"  Download Speed   : {speed_mbs:.2f} MB/s (est)")
                print(f"  ETA              : {eta_str}")
                print("=" * 68 + "\n", flush=True)

        # ── Extraction Consumer Thread ────────────────────────────────────────
        def consumer_task():
            while True:
                item = processing_queue.get()
                if item is SENTINEL:
                    processing_queue.task_done()
                    break

                yr, mo, nc_path = item
                label = f"{yr}-{mo:02d}"

                try:
                    logger.info(f"Consumer: Extracting {label} to Parquet...")
                    df_month = self.extract_station_values(nc_path, station_ids, station_coords)

                    if not df_month.empty and "station_id" in df_month.columns:
                        with self.lock:
                            for sid, grp in df_month.groupby("station_id"):
                                df_month_station = grp.drop(columns=["station_id"])
                                out = self.proc_dir / f"era5_{sid}.parquet"
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

                    # Delete NC immediately after extraction
                    if nc_path.exists():
                        nc_path.unlink()
                        logger.debug(f"Consumer: Deleted NetCDF {nc_path.name}")

                    with self.lock:
                        ok_months.append(label)

                except Exception as exc:
                    logger.error(f"Consumer error processing {label}: {exc}")
                    with self.lock:
                        fail_months.append(label)

                finally:
                    processing_queue.task_done()
                    print_progress()

        # Start consumer thread
        c_thread = threading.Thread(target=consumer_task, daemon=True)
        c_thread.start()

        # ── Download Producer Task ───────────────────────────────────────────
        def download_task(yr: int, mo: int):
            nc_path = self.raw_dir / f"era5_{yr}_{mo:02d}.nc"
            label = f"{yr}-{mo:02d}"

            with self.lock:
                active_downloads[label] = time.monotonic()
            print_progress()

            attempts = 5
            backoff = 10.0
            success = False

            for attempt in range(1, attempts + 1):
                try:
                    self.download_month(yr, mo, nc_path)
                    success = True
                    break
                except Exception as exc:
                    logger.warning(f"ERA5 {label}: Download error (Attempt {attempt}/{attempts}): {exc}")
                    if attempt < attempts:
                        sleep_time = backoff * (2 ** (attempt - 1))
                        time.sleep(sleep_time)

            with self.lock:
                if label in active_downloads:
                    del active_downloads[label]

            if success:
                processing_queue.put((yr, mo, nc_path))
            else:
                with self.lock:
                    fail_months.append(label)
                print_progress()

        # Submit tasks to executor with maximum 2 concurrent download workers
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(download_task, yr, mo) for yr, mo in to_process]
            for fut in futures:
                fut.result()  # blocks until download task finishes (which puts item in queue)

        # Signal consumer to terminate after all downloads finish
        processing_queue.put(SENTINEL)
        c_thread.join()

        # Perform final validation of Parquet files
        val_ok = self.validate_parquets(station_ids)

        status = "OK" if val_ok and not fail_months else "WARNING"
        notes = f"Processed {len(ok_months)} months. Gaps/Failures: {len(fail_months)}."
        if not val_ok:
            notes += " Parquet output validation failed."

        return {"status": status, "notes": notes}

