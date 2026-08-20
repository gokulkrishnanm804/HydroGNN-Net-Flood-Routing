"""
GPM IMERG Manual Ingestor
=========================
Processes NASA GPM IMERG HDF5 files that have been MANUALLY downloaded
and placed into the raw/gpm/ directory.

This module performs NO network requests and does NOT touch NASA Earthdata.
It only reads files that already exist on disk.

Directory convention expected by this ingestor:
    pipeline/dataset/raw/gpm/
        {YYYY}/
            {MM}/
                3B-HHR.MS.MRG.3IMERG.{YYYYMMDD}-S{HHMMSS}-E{HHMMSS}.{MFM}.V07B.HDF5
                ...
        (any subdirectory depth is supported — the ingestor walks the full tree)

Scientific contract (frozen — identical to GPMOptimizedDownloader):
    - extract_station_values() logic unchanged (nearest-pixel, fill→NaN)
    - Parquet schema: [timestamp, precipitation_mm_30min] per station
    - Station coordinates and CRS unchanged

Reference:
    Huffman, G.J. et al. (2020). Integrated Multi-satellitE Retrievals for GPM
    (IMERG). Algorithm Theoretical Basis Document V06.
    https://gpm.nasa.gov/sites/default/files/2020-05/IMERG_ATBD_V06.3.pdf
"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

from src.downloaders.gpm_imerg import GPMIMERGDownloader
from src.utils.cache import CacheManager
from src.utils.logger import DownloadLogger, get_logger

logger = get_logger(__name__)

# ─── Filename pattern for GPM IMERG HDF5 files ────────────────────────────────
# 3B-HHR.MS.MRG.3IMERG.20180115-S003000-E005959.0030.V07B.HDF5
_GPM_FNAME_RE = re.compile(
    r"3B-HHR\.MS\.MRG\.3IMERG\."
    r"(?P<date>\d{8})"          # YYYYMMDD
    r"-S(?P<start>\d{6})"       # SHHMMSS
    r"-E(?P<end>\d{6})"         # EHHMMSS
    r"\.(?P<mfm>\d{4})"         # MMMM  (minutes from midnight)
    r"\.V\d+[A-Z]\.HDF5$",
    re.IGNORECASE,
)


def _parse_timestamp(fname: str) -> Optional[pd.Timestamp]:
    """
    Parse the UTC start timestamp encoded in an IMERG HDF5 filename.

    Returns None if the filename does not match the expected pattern.
    """
    m = _GPM_FNAME_RE.search(fname)
    if not m:
        return None
    d_str = m.group("date")   # YYYYMMDD
    s_str = m.group("start")  # HHMMSS
    try:
        return pd.Timestamp(
            year=int(d_str[:4]),
            month=int(d_str[4:6]),
            day=int(d_str[6:8]),
            hour=int(s_str[:2]),
            minute=int(s_str[2:4]),
            second=0,
            tz="UTC",
        )
    except (ValueError, OverflowError):
        return None


class GPMManualIngestor(GPMIMERGDownloader):
    """
    Processes manually downloaded GPM IMERG HDF5 files.

    Inherits GPMIMERGDownloader to reuse:
        - extract_station_values()  ← scientific logic, frozen
        - save_station_extracts()   ← Parquet writer
        - _flush_buffers()          ← batch Parquet append

    This class performs NO downloads. It only reads HDF5 files already
    present in the raw/gpm/ directory tree.

    Safe to run multiple times — already-processed timestamps are skipped.
    Original HDF5 files are NEVER deleted or modified.
    """

    SOURCE = "GPM_MANUAL"

    def __init__(
        self,
        cache_manager: CacheManager,
        download_logger: DownloadLogger,
        config: dict,
    ) -> None:
        # Bypass GPMIMERGDownloader.__init__ credential check —
        # credentials are not needed for manual ingest (no network I/O).
        # We only call BaseDownloader.__init__ and set the fields we need.
        from src.downloaders.base import BaseDownloader
        BaseDownloader.__init__(self, cache_manager, download_logger, config)

        self.username = ""   # Not used — no network I/O
        self.password = ""
        self.bbox     = config["basin"]["bbox"]
        self.variable = config["gpm"]["variable"]          # "precipitationCal"
        self.raw_dir  = Path(config["paths"]["raw_dir"]) / "gpm"
        self.raw_dir.mkdir(parents=True, exist_ok=True)

        proc_dir = Path(config["paths"]["processed_dir"])
        proc_dir.mkdir(parents=True, exist_ok=True)
        logs_dir = Path(config["paths"]["logs_dir"])
        logs_dir.mkdir(parents=True, exist_ok=True)

        self._proc_dir   = proc_dir
        self._logs_dir   = logs_dir
        self._report_path = logs_dir / "gpm_manual_ingest_report.json"
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Scan raw/gpm/ for all HDF5 files
    # ------------------------------------------------------------------ #

    def scan_hdf5_files(self) -> List[Path]:
        """
        Recursively walk raw/gpm/ and return all matching HDF5 file paths,
        sorted chronologically by the timestamp encoded in the filename.
        """
        found: List[Tuple[pd.Timestamp, Path]] = []
        for p in self.raw_dir.rglob("*.HDF5"):
            ts = _parse_timestamp(p.name)
            if ts is None:
                # Try case-insensitive extension
                ts = _parse_timestamp(p.stem + ".HDF5")
            if ts is not None:
                found.append((ts, p))
            else:
                logger.warning(f"GPM Manual: skipping unrecognised filename: {p.name}")

        # Also try .hdf5 lowercase
        for p in self.raw_dir.rglob("*.hdf5"):
            ts = _parse_timestamp(p.stem.upper() + ".HDF5")
            if ts is not None and not any(q == p for _, q in found):
                found.append((ts, p))

        found.sort(key=lambda x: x[0])
        logger.info(f"GPM Manual: found {len(found)} HDF5 files in {self.raw_dir}")
        return [p for _, p in found]

    # ------------------------------------------------------------------ #
    # Load already-processed timestamps from existing Parquet files
    # ------------------------------------------------------------------ #

    def _load_processed_timestamps(self, station_ids: List[str]) -> Set[pd.Timestamp]:
        """
        Return the set of timestamps already present in any station's Parquet.
        Uses the first station's Parquet as the reference (all stations are
        written together, so they are always in sync).
        """
        processed: Set[pd.Timestamp] = set()
        # Use the first station's Parquet as the reference index
        for sid in station_ids:
            p = self._proc_dir / f"gpm_{sid}.parquet"
            if p.exists():
                try:
                    df = pd.read_parquet(p, columns=["timestamp"])
                    ts_series = pd.to_datetime(df["timestamp"], utc=True)
                    processed.update(ts_series.tolist())
                    logger.info(
                        f"GPM Manual: found {len(processed):,} already-processed "
                        f"timestamps in gpm_{sid}.parquet"
                    )
                    break   # One station is enough — all are in sync
                except Exception as e:
                    logger.warning(f"GPM Manual: could not read existing Parquet for {sid}: {e}")
        return processed

    # ------------------------------------------------------------------ #
    # Validate a single HDF5 file
    # ------------------------------------------------------------------ #

    def _validate_hdf5(self, path: Path) -> Tuple[bool, str]:
        """
        Validate an HDF5 file using h5py.

        Returns (is_valid, error_message).
        """
        import h5py
        try:
            with h5py.File(path, "r") as hf:
                grid = hf.get("Grid")
                if grid is None:
                    return False, "Missing /Grid group"
                if self.variable not in grid:
                    return False, f"Variable '{self.variable}' not in /Grid"
                # Quick shape check
                arr = grid[self.variable]
                if arr.ndim not in (2, 3):
                    return False, f"Unexpected array shape: {arr.shape}"
            return True, ""
        except OSError as e:
            return False, f"HDF5 read error: {e}"
        except Exception as e:
            return False, f"Unexpected error: {e}"

    # ------------------------------------------------------------------ #
    # Compute missing-date coverage report
    # ------------------------------------------------------------------ #

    def _compute_coverage(
        self,
        processed_ts: Set[pd.Timestamp],
        first_ts: Optional[pd.Timestamp],
        last_ts: Optional[pd.Timestamp],
    ) -> Dict:
        """
        Find all 30-min slots between first_ts and last_ts that are absent
        from the processed set.
        """
        if first_ts is None or last_ts is None:
            return {"missing_count": 0, "missing_dates": []}

        # Generate expected 30-min grid
        expected = pd.date_range(
            start=first_ts.normalize(),      # midnight of first date
            end=last_ts.normalize() + pd.Timedelta(hours=23, minutes=30),
            freq="30min",
            tz="UTC",
        )
        missing_ts = [t for t in expected if t not in processed_ts]
        # Group by date for readability
        missing_dates = sorted(set(t.date().isoformat() for t in missing_ts))
        return {
            "missing_slots": len(missing_ts),
            "missing_dates_count": len(missing_dates),
            "missing_dates_sample": missing_dates[:50],  # first 50 dates
        }

    # ------------------------------------------------------------------ #
    # Main entry point
    # ------------------------------------------------------------------ #

    def run(
        self,
        station_ids: List[str],
        station_coords: List[Tuple[float, float]],
        batch_size: int = 200,
    ) -> Dict:
        """
        Process all manually downloaded HDF5 files in raw/gpm/.

        Parameters
        ----------
        station_ids    : List of station ID strings (determines Parquet filenames).
        station_coords : List of (lat, lon) tuples aligned with station_ids.
        batch_size     : Flush Parquet every N successfully extracted files.

        Returns
        -------
        dict with keys:
            hdf5_found, processed, skipped, failed,
            coverage_start, coverage_end, missing_coverage
        """
        t_start = time.monotonic()

        # ── 1. Discover all HDF5 files ─────────────────────────────────
        all_files = self.scan_hdf5_files()
        n_found = len(all_files)

        if n_found == 0:
            msg = (
                f"No GPM HDF5 files found in {self.raw_dir}.\n"
                "Place manually downloaded files under:\n"
                "  pipeline/dataset/raw/gpm/{YYYY}/{MM}/"
                "3B-HHR.MS.MRG.3IMERG.{YYYYMMDD}-S{HHMMSS}-E{HHMMSS}.{MFM}.V07B.HDF5"
            )
            logger.warning(msg)
            return {
                "hdf5_found": 0, "processed": 0, "skipped": 0, "failed": 0,
                "coverage_start": None, "coverage_end": None,
                "missing_coverage": {}, "message": msg,
            }

        # ── 2. Load already-processed timestamps (for skip logic) ──────
        already_done = self._load_processed_timestamps(station_ids)
        logger.info(
            f"GPM Manual: {n_found} files to inspect | "
            f"{len(already_done):,} timestamps already processed"
        )

        # ── 3. Process files ────────────────────────────────────────────
        buffers: Dict[str, list] = {sid: [] for sid in station_ids}
        n_processed = 0
        n_skipped   = 0
        n_failed    = 0
        failed_files: List[Dict] = []

        all_ts_processed: Set[pd.Timestamp] = set(already_done)
        new_ts_processed: Set[pd.Timestamp] = set()

        for idx, hdf5_path in enumerate(all_files, 1):
            fname = hdf5_path.name
            ts    = _parse_timestamp(fname)
            if ts is None:
                logger.warning(f"GPM Manual: cannot parse timestamp from {fname}, skipping")
                n_failed += 1
                failed_files.append({"file": str(hdf5_path), "reason": "unparseable filename"})
                continue

            # Skip check
            if ts in already_done:
                n_skipped += 1
                logger.debug(f"GPM Manual: SKIP (already processed) {fname}")
                continue

            # Validate
            is_valid, err = self._validate_hdf5(hdf5_path)
            if not is_valid:
                logger.warning(f"GPM Manual: INVALID {fname}: {err}")
                n_failed += 1
                failed_files.append({"file": str(hdf5_path), "reason": err, "timestamp": str(ts)})
                continue

            # Extract — uses frozen scientific logic from GPMIMERGDownloader
            try:
                vals = self.extract_station_values(hdf5_path, station_ids, station_coords)
                for sid, val in vals.items():
                    buffers[sid].append((ts, val))
                n_processed += 1
                new_ts_processed.add(ts)
                logger.debug(f"GPM Manual: OK [{idx}/{n_found}] {fname}")
            except Exception as exc:
                logger.error(f"GPM Manual: extraction error {fname}: {exc}")
                n_failed += 1
                failed_files.append({"file": str(hdf5_path), "reason": str(exc), "timestamp": str(ts)})
                continue

            # Batch flush
            total_buf = sum(len(v) for v in buffers.values())
            if total_buf >= batch_size * len(station_ids):
                self._flush_buffers(buffers, station_ids, final=False)

            # Progress log every 480 files (~10 days worth)
            if idx % 480 == 0:
                pct = idx / n_found * 100
                elapsed = time.monotonic() - t_start
                rate = n_processed / max(elapsed, 1)
                logger.info(
                    f"GPM Manual progress: {pct:.1f}% | "
                    f"processed={n_processed:,} skipped={n_skipped:,} "
                    f"failed={n_failed} | {rate:.1f} files/s"
                )

        # ── 4. Final flush ──────────────────────────────────────────────
        self._flush_buffers(buffers, station_ids, final=True)

        # ── 5. Coverage analysis ────────────────────────────────────────
        all_ts_processed.update(new_ts_processed)
        sorted_ts = sorted(all_ts_processed)
        coverage_start = str(sorted_ts[0])  if sorted_ts else None
        coverage_end   = str(sorted_ts[-1]) if sorted_ts else None

        # Coverage gap analysis between first and last processed timestamp
        first_ts = sorted_ts[0]  if sorted_ts else None
        last_ts  = sorted_ts[-1] if sorted_ts else None
        missing  = self._compute_coverage(all_ts_processed, first_ts, last_ts)

        # ── 6. Build and save report ────────────────────────────────────
        elapsed_total = time.monotonic() - t_start
        report = {
            "generated_at":      pd.Timestamp.now("UTC").isoformat(),
            "raw_gpm_dir":       str(self.raw_dir),
            "hdf5_found":        n_found,
            "processed":         n_processed,
            "skipped_existing":  n_skipped,
            "failed":            n_failed,
            "total_processed_timestamps": len(all_ts_processed),
            "coverage_start":    coverage_start,
            "coverage_end":      coverage_end,
            "coverage_gaps":     missing,
            "failed_files":      failed_files[:100],  # cap at 100 for JSON size
            "elapsed_seconds":   round(elapsed_total, 1),
        }
        try:
            self._report_path.write_text(json.dumps(report, indent=2, default=str))
            logger.info(f"GPM Manual: report saved → {self._report_path}")
        except Exception as e:
            logger.warning(f"GPM Manual: could not save report: {e}")

        # ── 7. Print summary table ─────────────────────────────────────
        self._print_summary(report)
        return report

    # ------------------------------------------------------------------ #
    # Pretty-print summary
    # ------------------------------------------------------------------ #

    def _print_summary(self, report: Dict) -> None:
        """Print a formatted summary table to stdout."""
        sep = "=" * 68
        print(f"\n{sep}")
        print("  GPM IMERG Manual Ingest — Summary")
        print(sep)
        print(f"  HDF5 files found       : {report['hdf5_found']:,}")
        print(f"  Successfully processed : {report['processed']:,}")
        print(f"  Skipped (existing)     : {report['skipped_existing']:,}")
        print(f"  Failed (corrupt/parse) : {report['failed']}")
        print(f"  Total timestamps in DB : {report['total_processed_timestamps']:,}")
        print(f"  Coverage start         : {report['coverage_start'] or 'N/A'}")
        print(f"  Coverage end           : {report['coverage_end'] or 'N/A'}")
        gaps = report.get("coverage_gaps", {})
        print(f"  Missing 30-min slots   : {gaps.get('missing_slots', 0):,}")
        print(f"  Dates with gaps        : {gaps.get('missing_dates_count', 0):,}")
        if gaps.get("missing_dates_sample"):
            sample = gaps["missing_dates_sample"][:10]
            print(f"  Sample missing dates   : {', '.join(sample)}")
        print(f"  Elapsed                : {report['elapsed_seconds']:.1f}s")
        print(f"  Report saved to        : {self._report_path.name}")
        print(sep + "\n")

    # ------------------------------------------------------------------ #
    # Inherited Parquet batch-flush (redefined here to avoid coupling to
    # GPMOptimizedDownloader which has additional state we don't use)
    # ------------------------------------------------------------------ #

    def _flush_buffers(
        self,
        buffers: Dict[str, list],
        station_ids: List[str],
        final: bool,
    ) -> None:
        """
        Flush accumulated records to per-station Parquet files (append mode).

        Parquet schema (frozen): timestamp | precipitation_mm_30min
        Per-station file       : gpm_{station_id}.parquet
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
                    df_new   = (
                        df_new
                        .drop_duplicates(subset=["timestamp"])
                        .sort_values("timestamp")
                        .reset_index(drop=True)
                    )
                df_new.to_parquet(out, index=False)

            n = len(rows)
            logger.debug(
                f"GPM Manual: flushed {n:,} records for {sid} "
                f"{'(final)' if final else ''} → {out.name}"
            )
            buffers[sid] = []
