"""
CWC Reservoir Data Parser

Parses manually exported reservoir monitoring data from India-WRIS.
Export from: https://indiawris.gov.in/wris/#/
    Water Resources > Reservoir Monitoring > Daily Reservoir Data

Place files in: dataset/raw/reservoir/{RESERVOIR_ID}_{YYYY}.csv
Example: dataset/raw/reservoir/METTUR_2020.csv

This parser NEVER generates synthetic reservoir data.
If reservoir CSV files are absent, the pipeline uses zeros for
reservoir_release and reservoir_storage features and logs a WARNING.

Data Source: Central Water Commission / India-WRIS
    https://indiawris.gov.in
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger(__name__)

_IST_OFFSET = pd.Timedelta(hours=5, minutes=30)


class ReservoirDataParser:
    """
    Parser for CWC India-WRIS reservoir monitoring CSV exports.

    Supported formats:
    - WRIS_A : Date, Storage(%), Outflow(cumecs), Level(m)
    - WRIS_B : Date, Storage(MCM), Release(cumecs), Water Level
    - WRIS_C : Sl.No, Date & Time, Storage %, Release, Level
    """

    _STORAGE_COLS  = ["Storage(%)", "Storage (%)", "STORAGE (%)", "Storage(MCM)", "storage_pct"]
    _RELEASE_COLS  = ["Outflow(cumecs)", "Release(cumecs)", "Release", "RELEASE (CUMECS)", "release_cumecs"]
    _LEVEL_COLS    = ["Level(m)", "Water Level", "Water Level(m)", "WATER LEVEL", "level_m"]
    _CAPACITY_COLS = ["Capacity(MCM)", "Capacity", "Full Reservoir Level"]

    def __init__(self, raw_dir: Path, config: dict) -> None:
        self.res_dir = Path(raw_dir) / "reservoir"
        self.config  = config
        self.max_gap = config.get("preprocessing", {}).get("max_gap_fill_hours", 6)

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #

    def check_data_availability(self) -> Dict[str, List[int]]:
        """Scan reservoir dir for {RESERVOIR_ID}_{YYYY}.csv files."""
        self.res_dir.mkdir(parents=True, exist_ok=True)
        available: Dict[str, List[int]] = {}
        pattern = re.compile(r"^(.+?)_(\d{4})\.csv$", re.IGNORECASE)
        for f in self.res_dir.glob("*.csv"):
            m = pattern.match(f.name)
            if m:
                rid, yr = m.group(1).upper(), int(m.group(2))
                available.setdefault(rid, []).append(yr)
        for rid in available:
            available[rid] = sorted(available[rid])
        logger.info(f"Reservoir: found {len(available)} reservoirs: {list(available.keys())}")
        return available

    def report_missing_reservoirs(
        self,
        available: Dict[str, List[int]],
        required_ids: List[str],
    ) -> List[str]:
        """Log WARNING for each missing reservoir. Never generates data."""
        missing = []
        for rid in required_ids:
            if rid not in available:
                missing.append(rid)
                logger.warning(
                    f"Reservoir data MISSING: {rid}\n"
                    f"  Export from India-WRIS > Reservoir Monitoring\n"
                    f"  Save as: dataset/raw/reservoir/{rid}_{{YYYY}}.csv"
                )
        return missing

    # ------------------------------------------------------------------ #
    # Format detection
    # ------------------------------------------------------------------ #

    def _detect_reservoir_format(self, df_raw: pd.DataFrame) -> str:
        cols_str = " ".join(str(c) for c in df_raw.columns).lower()
        if "storage(%)" in cols_str or "storage (%)" in cols_str:
            return "WRIS_A"
        if "storage(mcm)" in cols_str or "release" in cols_str:
            return "WRIS_B"
        if "sl.no" in cols_str or "date & time" in cols_str:
            return "WRIS_C"
        return "WRIS_D"

    def _find_col(self, df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
        for c in candidates:
            for col in df.columns:
                if str(col).strip().lower() == c.lower():
                    return col
        return None

    # ------------------------------------------------------------------ #
    # Parsing
    # ------------------------------------------------------------------ #

    def parse_reservoir_csv(self, csv_path: Path, reservoir_id: str) -> pd.DataFrame:
        """
        Parse a single reservoir CSV file.

        Returns
        -------
        pd.DataFrame  UTC DatetimeIndex, columns=[storage_pct, release_cumecs, level_m].
        Values validated: storage_pct in [0,120], release >= 0, level > 0.
        """
        # Try encodings
        df = None
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                df_raw = pd.read_csv(csv_path, encoding=enc, header=None, dtype=str)
                # Find header row
                header_row = 0
                for i, row in df_raw.iterrows():
                    row_vals = " ".join(str(v).lower() for v in row.values)
                    if any(kw in row_vals for kw in ("date", "storage", "level", "release")):
                        header_row = i
                        break
                df = pd.read_csv(csv_path, encoding=enc, skiprows=header_row, dtype=str)
                df.columns = [str(c).strip() for c in df.columns]
                break
            except Exception:
                continue

        if df is None or df.empty:
            logger.error(f"Could not parse reservoir CSV: {csv_path}")
            return pd.DataFrame()

        fmt = self._detect_reservoir_format(df)

        # Find date column
        date_col = None
        for c in ["Date", "DATE", "Date & Time", "DATE & TIME"]:
            found = self._find_col(df, [c])
            if found:
                date_col = found
                break
        if date_col is None and len(df.columns) > 0:
            date_col = df.columns[0]

        # Parse timestamps (CWC reservoir data is typically daily, in IST)
        ts_ist = pd.to_datetime(df[date_col], dayfirst=True, errors="coerce")
        ts_utc = ts_ist - _IST_OFFSET

        # Find value columns
        sto_col = self._find_col(df, self._STORAGE_COLS)
        rel_col = self._find_col(df, self._RELEASE_COLS)
        lvl_col = self._find_col(df, self._LEVEL_COLS)
        cap_col = self._find_col(df, self._CAPACITY_COLS)

        def _to_float(col):
            if col is None:
                return pd.Series(np.nan, index=df.index)
            return pd.to_numeric(df[col], errors="coerce")

        storage_pct    = _to_float(sto_col)
        release_cumecs = _to_float(rel_col)
        level_m        = _to_float(lvl_col)

        # If storage is in MCM (not percent), we need capacity to convert
        if fmt == "WRIS_B" and cap_col:
            cap_mcm = _to_float(cap_col).fillna(method="ffill").iloc[0]
            if cap_mcm > 0:
                storage_pct = (storage_pct / cap_mcm * 100).clip(0, 120)
        elif fmt == "WRIS_B":
            # Attempt: look for a reservoir in config to get capacity
            for res_cfg in self.config.get("reservoirs", []):
                if res_cfg["id"] == reservoir_id:
                    cap_tmc = res_cfg.get("capacity_tmc", 0)
                    # 1 TMC = 28.317 MCM
                    cap_mcm = cap_tmc * 28.317
                    if cap_mcm > 0:
                        storage_pct = (storage_pct / cap_mcm * 100).clip(0, 120)
                    break

        out = pd.DataFrame({
            "timestamp":       ts_utc,
            "storage_pct":     storage_pct,
            "release_cumecs":  release_cumecs,
            "level_m":         level_m,
        }).dropna(subset=["timestamp"])

        # Validation
        bad_sto = (out["storage_pct"] < 0) | (out["storage_pct"] > 120)
        bad_rel = out["release_cumecs"] < 0
        bad_lvl = out["level_m"] <= 0
        n_bad = (bad_sto | bad_rel | bad_lvl).sum()
        if n_bad > 0:
            logger.warning(
                f"Reservoir {reservoir_id}: {n_bad} suspect values "
                f"(storage: {bad_sto.sum()}, release: {bad_rel.sum()}, level: {bad_lvl.sum()})"
            )

        return out.set_index("timestamp").sort_index()

    # ------------------------------------------------------------------ #
    # Alignment
    # ------------------------------------------------------------------ #

    def align_to_30min_grid(
        self,
        df: pd.DataFrame,
        max_gap_hours: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Resample daily reservoir data to 30-minute grid.

        CWC reservoir data is typically daily (once per day at 08:00 IST).
        Linear forward-fill is applied up to max_gap_hours (default 6h).
        For daily data, forward-fill across the full day is scientifically valid
        since reservoir levels change slowly.
        """
        if df.empty:
            return df
        max_gap_hours = max_gap_hours or self.max_gap
        # For daily data, 48 steps = 24h (forward-fill entire day)
        max_gap_steps = max(max_gap_hours * 2, 48)

        df_30 = df.resample("30T").interpolate(method="linear", limit=max_gap_steps)
        return df_30

    # ------------------------------------------------------------------ #
    # Load all
    # ------------------------------------------------------------------ #

    def load_all_available(
        self,
        reservoir_ids: List[str],
        years: List[int],
    ) -> Dict[str, pd.DataFrame]:
        """
        Load and combine all available reservoir CSV files.

        Returns {reservoir_id: aligned_df}.
        """
        available = self.check_data_availability()
        result: Dict[str, pd.DataFrame] = {}

        for rid in reservoir_ids:
            if rid not in available:
                continue
            yr_dfs = []
            for yr in years:
                if yr not in available[rid]:
                    continue
                csv_path = self.res_dir / f"{rid}_{yr}.csv"
                if not csv_path.exists():
                    csv_path = self.res_dir / f"{rid.lower()}_{yr}.csv"
                if not csv_path.exists():
                    continue
                parsed = self.parse_reservoir_csv(csv_path, rid)
                if not parsed.empty:
                    yr_dfs.append(parsed)

            if yr_dfs:
                combined = pd.concat(yr_dfs).sort_index()
                combined = combined[~combined.index.duplicated(keep="first")]
                aligned  = self.align_to_30min_grid(combined)
                result[rid] = aligned
                logger.info(
                    f"Reservoir {rid}: {len(aligned):,} 30-min rows "
                    f"({aligned.index.min()} to {aligned.index.max()})"
                )

        return result

    # ------------------------------------------------------------------ #
    # Save
    # ------------------------------------------------------------------ #

    def save_processed(
        self,
        data: Dict[str, pd.DataFrame],
        output_dir: Path,
    ) -> None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        for rid, df in data.items():
            out = output_dir / f"reservoir_{rid}.parquet"
            df.to_parquet(out)
            logger.debug(f"Saved: {out.name} ({len(df):,} rows)")
