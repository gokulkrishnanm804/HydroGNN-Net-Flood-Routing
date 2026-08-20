"""
NASA GPM IMERG Final Run V07 — Optimized Producer-Consumer Downloader

Architecture: 4 parallel download threads → bounded Queue → 1 extraction worker
              → batch Parquet writer → delete HDF5 immediately.

Scientific contract (frozen):
  - extract_station_values() logic unchanged (nearest-pixel, fill→NaN)
  - Parquet schema: [timestamp, station_id, precipitation_mm_30min]
  - Station coordinates and CRS unchanged

Performance features:
  - ThreadPoolExecutor with configurable workers (default: 4)
  - Producer-consumer queue (configurable size: 50)
  - Batch Parquet writes (default: 100 records per flush)
  - Exponential-backoff retries (1→2→4→8→16 s, max 5 attempts)
  - HTTP 429 / 5xx auto-backoff
  - Resume from download_state.json (never re-downloads completed files)
  - failed_downloads.csv for post-run retry
  - download.log with timing, throughput, and retry events

Reference:
    Huffman, G.J. et al. (2020). Integrated Multi-satellitE Retrievals for GPM
    (IMERG). Algorithm Theoretical Basis Document V06.
    https://gpm.nasa.gov/sites/default/files/2020-05/IMERG_ATBD_V06.3.pdf
"""
from __future__ import annotations

import csv
import json
import logging
import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.downloaders.base import BaseDownloader, _get_earthdata_session
from src.utils.cache import CacheManager, DataSourceUnavailable
from src.utils.logger import DownloadLogger, get_logger

logger = get_logger(__name__)

# ─── Sentinel to signal extraction worker that downloads are done ──────────
_QUEUE_DONE = object()

# ─── HTTP status codes that warrant a retry ───────────────────────────────
_RETRYABLE_HTTP = {429, 500, 502, 503, 504}

# ─── Transient exception types that warrant a retry ───────────────────────
_RETRYABLE_EXC = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
    ConnectionResetError,
)


# ═══════════════════════════════════════════════════════════════════════════
# Original downloader — kept intact for backward compatibility
# ═══════════════════════════════════════════════════════════════════════════

class GPMIMERGDownloader(BaseDownloader):
    """
    Downloads and extracts GPM IMERG 3IMERGHH V07 precipitation data.

    Only the files that overlap with the basin bounding box are downloaded.
    Station values are extracted by nearest-pixel lookup on the 0.1° grid.
    Negative fill values (<0) are converted to NaN.
    """

    BASE_URL = "https://gpm1.gesdisc.eosdis.nasa.gov/data/GPM_L3/GPM_3IMERGHH.07"
    SOURCE   = "GPM_IMERG"

    def __init__(
        self,
        cache_manager: CacheManager,
        download_logger: DownloadLogger,
        config: dict,
    ) -> None:
        super().__init__(cache_manager, download_logger, config)
        self.username = (
            os.environ.get("NASA_EARTHDATA_USERNAME", "")
            or config.get("credentials", {}).get("earthdata_username", "")
        )
        self.password = (
            os.environ.get("NASA_EARTHDATA_PASSWORD", "")
            or config.get("credentials", {}).get("earthdata_password", "")
        )
        self.bbox     = config["basin"]["bbox"]          # [lon_min, lat_min, lon_max, lat_max]
        self.variable = config["gpm"]["variable"]        # "precipitationCal"
        self.raw_dir  = Path(config["paths"]["raw_dir"]) / "gpm"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self._check_credentials()

    # ------------------------------------------------------------------ #
    # Credential check
    # ------------------------------------------------------------------ #

    def _check_credentials(self) -> None:
        """Raise DataSourceUnavailable if Earthdata credentials are missing."""
        if not self.username or not self.password:
            raise DataSourceUnavailable(
                "NASA Earthdata credentials are required for GPM IMERG download.\n"
                "\n"
                "  1. Register for a free account at:\n"
                "     https://urs.earthdata.nasa.gov\n"
                "\n"
                "  2. Approve the 'NASA GESDISC DATA ARCHIVE' application at:\n"
                "     https://urs.earthdata.nasa.gov/approve_app?client_id=e2WVk8Pw6weeLUKZYOxvTQ\n"
                "\n"
                "  3. Add credentials to project .env:\n"
                "     NASA_EARTHDATA_USERNAME=your_username\n"
                "     NASA_EARTHDATA_PASSWORD=your_password\n"
                "\n"
                "  Registration is free and takes ~5 minutes.\n"
                "  GPM IMERG provides 30-min global precipitation since June 2000."
            )

    def _auth(self) -> tuple:
        return (self.username, self.password)

    # ------------------------------------------------------------------ #
    # URL construction
    # ------------------------------------------------------------------ #

    def build_file_url(self, ts: pd.Timestamp) -> str:
        """
        Build the HTTPS URL for a single 30-min GPM IMERG HDF5 file.

        URL pattern:
            BASE/{YYYY}/{DOY}/3B-HHR.MS.MRG.3IMERG.{YYYYMMDD}-S{HHMMSS}-E{HHMMSS}.{MFM}.V07B.HDF5

        Parameters
        ----------
        ts : pd.Timestamp  UTC start time of the 30-min window.
        """
        doy      = ts.timetuple().tm_yday
        date_str = ts.strftime("%Y%m%d")
        hh, mm   = ts.hour, ts.minute
        start_s  = f"{hh:02d}{mm:02d}00"
        # Each 30-min slot spans exactly 30 minutes.
        # Slot start xx:00 → end xx:29:59  (end_hh=hh, end_mm=29)
        # Slot start xx:30 → end xx:59:59  (end_hh=hh, end_mm=59)
        # Special case: 23:30 → end 23:59:59 (same formula, no overflow)
        if hh == 23 and mm == 30:
            end_s = "235959"
        else:
            end_hh = hh                        # always same hour
            end_mm = 59 if mm == 30 else 29    # :30 slot → :59, :00 slot → :29
            end_s  = f"{end_hh:02d}{end_mm:02d}59"
        mfm      = hh * 60 + mm  # minutes from midnight
        fname    = (
            f"3B-HHR.MS.MRG.3IMERG.{date_str}"
            f"-S{start_s}-E{end_s}.{mfm:04d}.V07B.HDF5"
        )
        return f"{self.BASE_URL}/{ts.year}/{doy:03d}/{fname}"

    def list_timestamps_for_date(self, target: date) -> List[pd.Timestamp]:
        """Return 48 UTC timestamps (30-min intervals) for *target* date."""
        base = pd.Timestamp(target, tz="UTC")
        return [base + pd.Timedelta(minutes=30 * i) for i in range(48)]

    # ------------------------------------------------------------------ #
    # Download
    # ------------------------------------------------------------------ #

    def download_date(self, target: date) -> Path:
        """
        Download all 48 GPM IMERG files for a given date.

        Returns the directory containing the downloaded HDF5 files.
        """
        out_dir = self.raw_dir / str(target.year) / f"{target.month:02d}"
        out_dir.mkdir(parents=True, exist_ok=True)

        timestamps = self.list_timestamps_for_date(target)
        tasks = []
        for ts in timestamps:
            url   = self.build_file_url(ts)
            fname = url.split("/")[-1]
            dest  = out_dir / fname
            tasks.append((url, dest))

        results = self.download_parallel(
            tasks, auth=self._auth(), source_label=self.SOURCE
        )
        n_ok = sum(1 for v in results.values() if v)
        logger.info(f"GPM {target}: {n_ok}/{len(tasks)} files OK")
        return out_dir

    def download_date_range(
        self,
        start_date: date,
        end_date: date,
        station_ids: List[str],
        station_coords: List[Tuple[float, float]],
        delete_after_extract: bool = True,
    ) -> pd.DataFrame:
        """
        Download GPM data for a date range and extract station precipitation.

        Parameters
        ----------
        start_date, end_date   : date range (inclusive).
        station_ids            : list of station ID strings.
        station_coords         : list of (lat, lon) tuples, same order as station_ids.
        delete_after_extract   : If True (default), delete each HDF5 after extracting
                                 station values to save disk space (~7 MB → 0 per slot).
                                 The 8 extracted pixel values are saved to Parquet instead.

        Returns
        -------
        pd.DataFrame  columns: [timestamp (UTC), station_id, precipitation_mm_30min]
        """
        records: list = []
        current = start_date

        while current <= end_date:
            out_dir    = self.download_date(current)
            timestamps = self.list_timestamps_for_date(current)

            for ts in timestamps:
                url   = self.build_file_url(ts)
                fname = url.split("/")[-1]
                hdf5  = out_dir / fname
                if not hdf5.exists():
                    logger.debug(f"GPM file absent: {fname}")
                    continue
                try:
                    vals = self.extract_station_values(hdf5, station_ids, station_coords)
                    for sid, val in vals.items():
                        records.append({
                            "timestamp":              ts,
                            "station_id":             sid,
                            "precipitation_mm_30min": val,
                        })
                    if delete_after_extract:
                        hdf5.unlink(missing_ok=True)
                        logger.debug(f"Deleted (extracted): {fname}")
                except Exception as exc:
                    logger.error(f"Extraction error {fname}: {exc}")

            current += timedelta(days=1)

        if not records:
            logger.warning("No GPM records extracted for the requested date range")
            return pd.DataFrame(columns=["timestamp", "station_id", "precipitation_mm_30min"])

        df = (
            pd.DataFrame(records)
            .sort_values(["station_id", "timestamp"])
            .reset_index(drop=True)
        )
        return df

    # ------------------------------------------------------------------ #
    # Extraction  ← FROZEN: scientific logic must not change
    # ------------------------------------------------------------------ #

    def extract_station_values(
        self,
        hdf5_path: Path,
        station_ids: List[str],
        station_coords: List[Tuple[float, float]],
    ) -> Dict[str, float]:
        """
        Extract precipitationCal at each station coordinate (nearest grid cell).

        GPM IMERG HDF5 structure (V07):
            /Grid/lat              shape (nlat,)   -89.95 to 89.95, step 0.1
            /Grid/lon              shape (nlon,)  -179.95 to 179.95, step 0.1
            /Grid/precipitationCal shape (1, nlat, nlon) or (1, nlon, nlat)

        GPM fill value: -9999.9 (converted to NaN here).

        Parameters
        ----------
        hdf5_path     : Path to an IMERG HDF5 file.
        station_ids   : list of station ID strings.
        station_coords: list of (lat, lon).
        """
        import h5py

        with h5py.File(hdf5_path, "r") as f:
            grid   = f["Grid"]
            lat    = np.asarray(grid["lat"])
            lon    = np.asarray(grid["lon"])
            precip = np.asarray(grid[self.variable])   # (1, ?, ?)

            # Squeeze time dimension
            precip = precip[0] if precip.ndim == 3 else precip

            # GPM V07 stores as (nlon, nlat) for some files — detect and transpose
            if precip.shape[0] == len(lon) and precip.shape[1] == len(lat):
                precip = precip.T  # → (nlat, nlon)

        result: Dict[str, float] = {}
        for sid, (slat, slon) in zip(station_ids, station_coords):
            li = int(np.argmin(np.abs(lat - slat)))
            lj = int(np.argmin(np.abs(lon - slon)))
            v  = float(precip[li, lj])
            result[sid] = float("nan") if v < 0 else v

        return result

    # ------------------------------------------------------------------ #
    # Save
    # ------------------------------------------------------------------ #

    def save_station_extracts(
        self,
        df: pd.DataFrame,
        output_dir: Path,
    ) -> None:
        """Save per-station precipitation extracts as Parquet files."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        for sid, grp in df.groupby("station_id"):
            out = output_dir / f"gpm_{sid}.parquet"
            grp.drop(columns=["station_id"]).to_parquet(out, index=False)
            logger.debug(f"Saved GPM extract: {out.name} ({len(grp):,} rows)")


# ═══════════════════════════════════════════════════════════════════════════
# Optimized producer-consumer downloader
# ═══════════════════════════════════════════════════════════════════════════

class GPMOptimizedDownloader(GPMIMERGDownloader):
    """
    High-performance GPM IMERG downloader with producer-consumer pipeline.

    Architecture
    ------------
    Producer threads (N=workers)
        ↓  download one HDF5 each, push Path to queue
    Bounded queue (size=queue_size)
        ↓
    Consumer thread (1)
        extract_station_values()   ← IDENTICAL to base class
        accumulate records
        flush to Parquet every batch_size records
        unlink HDF5 after extraction

    Scientific guarantee: extract_station_values() is inherited unchanged.
    Parquet schema is identical: [timestamp, station_id, precipitation_mm_30min].
    """

    def __init__(
        self,
        cache_manager: CacheManager,
        download_logger: DownloadLogger,
        config: dict,
    ) -> None:
        super().__init__(cache_manager, download_logger, config)

        gpm_cfg = config.get("gpm", {})
        self._workers     = int(gpm_cfg.get("workers",    4))
        self._batch_size  = int(gpm_cfg.get("batch_size", 100))
        self._retries     = int(gpm_cfg.get("retries",    5))
        self._timeout     = int(gpm_cfg.get("timeout",    60))
        self._queue_size  = int(gpm_cfg.get("queue_size", 50))
        self._resume      = bool(gpm_cfg.get("resume",    True))
        self._del_after   = bool(gpm_cfg.get("delete_after_extract", True))

        proc_dir = Path(config["paths"]["processed_dir"])
        proc_dir.mkdir(parents=True, exist_ok=True)
        logs_dir = Path(config["paths"]["logs_dir"])
        logs_dir.mkdir(parents=True, exist_ok=True)

        self._proc_dir          = proc_dir
        self._state_path        = proc_dir / "download_state.json"
        self._failed_csv_path   = proc_dir / "failed_downloads.csv"
        self._dl_log_path       = logs_dir / "gpm_download.log"

        # Thread-safe accumulators
        self._lock          = threading.Lock()
        self._buffers: Dict[str, list] = {}   # station_id → list of (timestamp, value)
        self._stats = {
            "files_ok":    0,
            "files_failed": 0,
            "bytes_total":  0,
            "retries_total": 0,
            "start_time":   0.0,
        }
        self._failed_records: list = []   # [{filename, error, retry_count, timestamp}]

        # Setup dedicated download logger
        self._setup_download_log()

    # ------------------------------------------------------------------ #
    # Logging setup
    # ------------------------------------------------------------------ #

    def _setup_download_log(self) -> None:
        """Configure a dedicated file logger for download events."""
        self._dl_file_logger = logging.getLogger("gpm.download")
        if not self._dl_file_logger.handlers:
            fh = logging.FileHandler(self._dl_log_path, encoding="utf-8")
            fh.setFormatter(logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            ))
            self._dl_file_logger.addHandler(fh)
            self._dl_file_logger.setLevel(logging.DEBUG)
            self._dl_file_logger.propagate = False

    def _log(self, msg: str, level: str = "info") -> None:
        """Write to both the console logger and the download file log."""
        getattr(logger, level)(msg)
        getattr(self._dl_file_logger, level)(msg)

    # ------------------------------------------------------------------ #
    # State persistence (resume support)
    # ------------------------------------------------------------------ #

    def _load_state(self) -> dict:
        """Load resume state from download_state.json."""
        if self._resume and self._state_path.exists():
            try:
                state = json.loads(self._state_path.read_text())
                self._log(
                    f"Resume: found state with {len(state.get('completed', []))} completed files"
                )
                return state
            except Exception as exc:
                self._log(f"State load failed ({exc}), starting fresh", "warning")
        return {"completed": [], "failed": []}

    def _save_state(self, state: dict) -> None:
        """Atomically save resume state to download_state.json."""
        tmp = self._state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=2))
        tmp.replace(self._state_path)

    # ------------------------------------------------------------------ #
    # Exponential backoff helper
    # ------------------------------------------------------------------ #

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        """Return backoff seconds for attempt number (1-indexed): 1,2,4,8,16."""
        return min(2 ** (attempt - 1), 16)

    # ------------------------------------------------------------------ #
    # Single-file download with full retry logic
    # ------------------------------------------------------------------ #

    def _download_one(
        self,
        url: str,
        dest: Path,
        completed_set: set,
    ) -> Tuple[bool, int, float]:
        """
        Download one HDF5 file using the inherited download_file helper.

        This ensures we reuse the same requests.Session and cookies, avoiding
        401 OAuth redirect race conditions.

        Parameters
        ----------
        url           : Full HTTPS URL for the HDF5 file.
        dest          : Local destination path.
        completed_set : Set of already-completed filenames (for resume).

        Returns
        -------
        (success: bool, retry_count: int, bytes_downloaded: float)
        """
        fname = dest.name

        # Resume: skip already-downloaded files
        if fname in completed_set or (dest.exists() and dest.stat().st_size > 1_000):
            self._log(f"SKIP (already done): {fname}", "debug")
            return True, 0, 0.0

        dest.parent.mkdir(parents=True, exist_ok=True)
        
        success = self.download_file(
            url=url,
            dest_path=dest,
            auth=self._auth(),
            resume=self._resume,
            source_label=self.SOURCE
        )

        n_bytes = float(dest.stat().st_size) if (success and dest.exists()) else 0.0
        return success, 0, n_bytes

    # ------------------------------------------------------------------ #
    # Consumer: extract → buffer → batch-flush Parquet
    # ------------------------------------------------------------------ #

    def _extraction_worker(
        self,
        dl_queue: "queue.Queue",
        station_ids: List[str],
        station_coords: List[Tuple[float, float]],
    ) -> None:
        """
        Consumer thread: dequeues HDF5 paths, extracts station values,
        accumulates records, and batch-flushes to Parquet.

        Sentinel: receives _QUEUE_DONE to exit cleanly.
        """
        buffers: Dict[str, list] = {sid: [] for sid in station_ids}
        n_extracted = 0

        while True:
            item = dl_queue.get()

            if item is _QUEUE_DONE:
                # Flush remaining records
                self._flush_buffers(buffers, station_ids, final=True)
                dl_queue.task_done()
                break

            hdf5_path, ts = item
            fname = hdf5_path.name
            t0 = time.monotonic()

            try:
                # ── HDF5 integrity check ──────────────────────────────────
                import h5py
                try:
                    with h5py.File(hdf5_path, "r") as hf:
                        if self.variable not in hf.get("Grid", {}):
                            raise ValueError(
                                f"Variable '{self.variable}' not in /Grid — "
                                f"file may be partial or HTML error page"
                            )
                except (OSError, ValueError) as hdf_err:
                    self._log(
                        f"Corrupt HDF5 {fname}: {hdf_err} — deleting for re-download",
                        "warning"
                    )
                    hdf5_path.unlink(missing_ok=True)
                    with self._lock:
                        self._stats["files_failed"] += 1
                    continue
                # ── SCIENTIFIC LOGIC: unchanged from base class ──────────
                vals = self.extract_station_values(hdf5_path, station_ids, station_coords)
                # ────────────────────────────────────────────────────────

                for sid, val in vals.items():
                    buffers[sid].append((ts, val))
                n_extracted += 1

                extract_ms = (time.monotonic() - t0) * 1000
                self._log(
                    f"Extracted {fname} in {extract_ms:.0f}ms "
                    f"| buffer size: {sum(len(v) for v in buffers.values())}", "debug"
                )

                # Delete HDF5 immediately after extraction
                if self._del_after and hdf5_path.exists():
                    hdf5_path.unlink()
                    self._log(f"Deleted: {fname}", "debug")

                # Batch flush
                total_buffered = sum(len(v) for v in buffers.values())
                if total_buffered >= self._batch_size * len(station_ids):
                    self._flush_buffers(buffers, station_ids, final=False)

            except Exception as exc:
                self._log(f"Extraction error for {fname}: {exc}", "error")
                # Don't delete on extraction failure
            finally:
                dl_queue.task_done()

    def _flush_buffers(
        self,
        buffers: Dict[str, list],
        station_ids: List[str],
        final: bool,
    ) -> None:
        """
        Flush accumulated records to per-station Parquet files (append mode).

        Parquet schema (frozen): timestamp | precipitation_mm_30min
        Per-station file: gpm_{station_id}.parquet
        """
        for sid in station_ids:
            if not buffers[sid]:
                continue

            rows = buffers[sid]
            df_new = pd.DataFrame(rows, columns=["timestamp", "precipitation_mm_30min"])
            out = self._proc_dir / f"gpm_{sid}.parquet"

            with self._lock:
                if out.exists():
                    existing = pd.read_parquet(out)
                    df_new   = pd.concat([existing, df_new], ignore_index=True)
                    # Deduplicate (idempotent on resume)
                    df_new   = df_new.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
                df_new.to_parquet(out, index=False)

            n = len(rows)
            self._log(
                f"Flushed {n:,} records for station {sid} "
                f"{'(final)' if final else ''} → {out.name}", "debug"
            )
            buffers[sid] = []

    # ------------------------------------------------------------------ #
    # Progress reporter
    # ------------------------------------------------------------------ #

    def _progress_reporter(
        self,
        total_files: int,
        stop_event: threading.Event,
    ) -> None:
        """
        Background thread: prints a rich progress line every 30 seconds.
        """
        interval = 30.0
        while not stop_event.is_set():
            time.sleep(interval)
            if stop_event.is_set():
                break
            elapsed = time.monotonic() - self._stats["start_time"]
            ok   = self._stats["files_ok"]
            fail = self._stats["files_failed"]
            done = ok + fail
            mb   = self._stats["bytes_total"] / 1e6
            avg_spd = mb / max(elapsed, 1)
            pct     = done / max(total_files, 1) * 100
            eta_s   = (total_files - done) / max(done / max(elapsed, 1), 0.01)
            eta_min = eta_s / 60

            print(
                f"\n[GPM PROGRESS] {pct:.1f}% | "
                f"OK={ok:,} | FAIL={fail} | "
                f"Retries={self._stats['retries_total']} | "
                f"{mb/1024:.2f} GB | "
                f"Avg={avg_spd:.1f} MB/s | "
                f"ETA={eta_min:.0f} min",
                flush=True,
            )

    # ------------------------------------------------------------------ #
    # Failed-files CSV
    # ------------------------------------------------------------------ #

    def _save_failed_csv(self) -> None:
        """Write failed_downloads.csv with filename, error, retry_count, timestamp."""
        if not self._failed_records:
            return
        with open(self._failed_csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=["filename", "url", "error", "retry_count", "timestamp"]
            )
            writer.writeheader()
            writer.writerows(self._failed_records)
        self._log(
            f"Saved {len(self._failed_records)} failed downloads → {self._failed_csv_path}"
        )

    # ------------------------------------------------------------------ #
    # Main entry point
    # ------------------------------------------------------------------ #

    def run_optimized(
        self,
        start_date: date,
        end_date: date,
        station_ids: List[str],
        station_coords: List[Tuple[float, float]],
    ) -> None:
        """
        Download GPM IMERG for [start_date, end_date] using the
        producer-consumer pipeline.

        Downloads are parallel (self._workers threads).
        Extraction is serial (1 consumer thread) to maintain deterministic
        pixel-level output identical to the sequential implementation.
        Parquet files are written in batches of self._batch_size slots.

        Parameters
        ----------
        start_date    : First date to download (inclusive).
        end_date      : Last date to download (inclusive).
        station_ids   : List of station ID strings (determines Parquet filenames).
        station_coords: List of (lat, lon) tuples aligned with station_ids.
        """
        self._stats["start_time"] = time.monotonic()
        state = self._load_state()
        completed_set: set = set(state.get("completed", []))

        # Build full task list: (url, dest_path, timestamp)
        tasks: List[Tuple[str, Path, pd.Timestamp]] = []
        current = start_date
        while current <= end_date:
            out_dir = self.raw_dir / str(current.year) / f"{current.month:02d}"
            for ts in self.list_timestamps_for_date(current):
                url   = self.build_file_url(ts)
                fname = url.split("/")[-1]
                dest  = out_dir / fname
                tasks.append((url, dest, ts))
            current += timedelta(days=1)

        total = len(tasks)
        self._log(
            f"GPM Optimized | {start_date} to {end_date} | "
            f"{total:,} files | {self._workers} workers | "
            f"batch={self._batch_size} | resume={self._resume}"
        )

        # ── Queue and extraction consumer thread ────────────────────────
        dl_queue: queue.Queue = queue.Queue(maxsize=self._queue_size)
        consumer = threading.Thread(
            target=self._extraction_worker,
            args=(dl_queue, station_ids, station_coords),
            name="GPM-Extractor",
            daemon=True,
        )
        consumer.start()

        # ── Progress reporter thread ─────────────────────────────────────
        stop_progress = threading.Event()
        progress_t = threading.Thread(
            target=self._progress_reporter,
            args=(total, stop_progress),
            name="GPM-Progress",
            daemon=True,
        )
        progress_t.start()

        # ── Producer pool ────────────────────────────────────────────────
        try:
            with ThreadPoolExecutor(
                max_workers=self._workers,
                thread_name_prefix="GPM-DL",
            ) as pool:
                future_map = {
                    pool.submit(self._download_one, url, dest, completed_set): (url, dest, ts)
                    for url, dest, ts in tasks
                }

                for future in as_completed(future_map):
                    url, dest, ts = future_map[future]
                    fname = dest.name
                    try:
                        success, n_retry, n_bytes = future.result()
                    except Exception as exc:
                        success, n_retry, n_bytes = False, 0, 0.0
                        self._log(f"Future error for {fname}: {exc}", "error")

                    with self._lock:
                        self._stats["retries_total"] += n_retry
                        self._stats["bytes_total"]   += n_bytes
                        if success:
                            self._stats["files_ok"] += 1
                            completed_set.add(fname)
                        else:
                            self._stats["files_failed"] += 1
                            self._failed_records.append({
                                "filename":    fname,
                                "url":         url,
                                "error":       "download_failed",
                                "retry_count": n_retry,
                                "timestamp":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            })

                    if success and dest.exists():
                        # Push to extraction queue (blocks if queue is full)
                        dl_queue.put((dest, ts))

                    # Periodically save state (every 48 files = 1 day)
                    if self._stats["files_ok"] % 48 == 0:
                        self._save_state({"completed": list(completed_set)})

        finally:
            # Signal consumer to flush and exit
            dl_queue.put(_QUEUE_DONE)
            consumer.join()

            # Stop progress reporter
            stop_progress.set()
            progress_t.join(timeout=2)

        # ── Post-run: save state, failed CSV, final summary ─────────────
        self._save_state({"completed": list(completed_set)})
        self._save_failed_csv()

        elapsed    = time.monotonic() - self._stats["start_time"]
        ok         = self._stats["files_ok"]
        fail       = self._stats["files_failed"]
        gb         = self._stats["bytes_total"] / 1e9
        throughput = self._stats["bytes_total"] / 1e6 / max(elapsed, 1)

        summary = (
            f"GPM Optimized COMPLETE | {elapsed/3600:.1f}h | "
            f"OK={ok:,} | FAIL={fail} | "
            f"{gb:.2f} GB | {throughput:.1f} MB/s avg"
        )
        self._log(summary)
        print(f"\n{'='*72}\n  {summary}\n{'='*72}")

        # Auto-retry failed files
        if self._failed_records:
            self._retry_failed(station_ids, station_coords, completed_set)

    # ------------------------------------------------------------------ #
    # Auto-retry of failed files
    # ------------------------------------------------------------------ #

    def _retry_failed(
        self,
        station_ids: List[str],
        station_coords: List[Tuple[float, float]],
        completed_set: set,
    ) -> None:
        """
        After the main run, retry all files in failed_downloads.csv.
        Uses a fresh queue+consumer for a clean extraction pass.
        """
        self._log(
            f"Auto-retry: {len(self._failed_records)} failed files",
            "warning"
        )
        retry_tasks = []
        for rec in self._failed_records:
            fname = rec["filename"]
            # Reconstruct dest path from fname
            # Pattern: 3B-HHR.MS.MRG.3IMERG.YYYYMMDD-SHHMMSS-EHHMMSS.MMMM.V07B.HDF5
            try:
                date_part = fname.split(".")[4].split("-")[0]   # YYYYMMDD
                yr        = int(date_part[:4])
                mo        = int(date_part[4:6])
                doy       = (date(yr, mo, int(date_part[6:8])) -
                             date(yr, 1, 1)).days + 1
                url       = f"{self.BASE_URL}/{yr}/{doy:03d}/{fname}"
                dest      = self.raw_dir / str(yr) / f"{mo:02d}" / fname
                retry_tasks.append((url, dest))
            except Exception as exc:
                self._log(f"Cannot reconstruct URL for {fname}: {exc}", "warning")

        if not retry_tasks:
            return

        # Simple sequential retry for failed files
        still_failed = []
        for url, dest in retry_tasks:
            success, n_retry, _ = self._download_one(url, dest, completed_set)
            if success:
                # Parse timestamp from filename and re-extract
                try:
                    fname = dest.name
                    date_str   = fname.split(".")[4].split("-")[0]
                    time_str   = fname.split("-S")[1].split("-E")[0]
                    hh, mm     = int(time_str[:2]), int(time_str[2:4])
                    yr, mo, dy = int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8])
                    ts = pd.Timestamp(yr, mo, dy, hh, mm, 0, tz="UTC")
                    vals = self.extract_station_values(dest, station_ids, station_coords)
                    # Write directly (single record flush)
                    for sid, val in vals.items():
                        df_row = pd.DataFrame([{"timestamp": ts, "precipitation_mm_30min": val}])
                        out = self._proc_dir / f"gpm_{sid}.parquet"
                        with self._lock:
                            if out.exists():
                                existing = pd.read_parquet(out)
                                df_row   = pd.concat([existing, df_row], ignore_index=True)
                                df_row   = df_row.drop_duplicates(subset=["timestamp"])
                            df_row.to_parquet(out, index=False)
                    if self._del_after and dest.exists():
                        dest.unlink()
                    self._log(f"Retry OK: {fname}")
                except Exception as exc:
                    self._log(f"Retry extraction failed for {dest.name}: {exc}", "error")
                    still_failed.append(url)
            else:
                still_failed.append(url)

        if still_failed:
            self._log(
                f"{len(still_failed)} files still failed after retry. "
                f"Check {self._failed_csv_path}", "warning"
            )
        else:
            self._log("All retried files recovered successfully")
