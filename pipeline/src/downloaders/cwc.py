"""
Central Water Commission (CWC) River Gauge Data Parser

IMPORTANT: CWC does NOT provide a public download API.
Historical river level and discharge data must be manually exported from:
    India-WRIS Portal: https://indiawris.gov.in/wris/#/
    Navigate to: Water Resources > Hydrological Observation > Daily Gauge Data

Place exported CSV files in the raw data directory:
    dataset/raw/cwc/{STATION_ID}_{YYYY}.csv
    Or place combined multi-station files:
    dataset/raw/cwc/cauvery_1991_2020.csv
    dataset/raw/cwc/cauvery_2021_2025.csv

This parser NEVER generates synthetic data. If a station has no CSV files,
it reports the station as unavailable and continues.

Data Source: Central Water Commission, Government of India
    https://cwc.gov.in
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

# IST offset: UTC+5:30
_IST_OFFSET = pd.Timedelta(hours=5, minutes=30)

# Mapping from config station ID to CWC Station name in combined CSV files
CWC_STATION_MAP = {
    "BILIGUNDLU":   "BILIGUNDULU",
    "METTUR_DAM":   "Mettur Reservoir",
    "ERODE":        "PALLIPALAYAM/Erode",
    "KODUMUDI":     "KODUMUDI",
    "KARUR":        "KODUMUDI",  # Fallback: KODUMUDI is the nearest CWC station
    "MUSIRI":       "MUSIRI",
    "TRICHY_UPPER": "UPPER ANICUT",
    "GRAND_ANICUT": "SRI RANGAM",  # Fallback: SRI RANGAM is closest CWC station to Grand Anicut
}


class CWCDataParser:
    """
    Parser for manually exported CWC India-WRIS gauge data.

    Never generates synthetic values. If CSV files are absent for a station,
    the station is reported as missing and skipped.
    """

    # Known CWC CSV column name patterns
    _LEVEL_COLS  = ["Water Level (m)", "Water Level (m CG)", "WL(m)", "WATER LEVEL (M)", "level_m", "River Water Level Telemetry Hourly (meter)"]
    _DISCH_COLS  = ["Discharge (cumecs)", "Discharge (Cumecs)", "Q(cumecs)", "DISCHARGE (CUMECS)", "discharge_cumecs"]
    _DATE_COLS   = ["Date", "Date & Time", "DATE", "DATE & TIME", "Sl.No", "Data Acquisition Time"]
    _TIME_COLS   = ["Time", "TIME"]

    def __init__(self, raw_dir: Path, config: dict) -> None:
        self.cwc_dir  = Path(raw_dir) / "cwc"
        self.config   = config
        self.max_gap  = config.get("preprocessing", {}).get("max_gap_fill_hours", 6)

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #

    def check_data_availability(self) -> Dict[str, List[int]]:
        """
        Scan cwc_dir for CSV files matching {STATION_ID}_{YYYY}.csv or combined files.

        Returns
        -------
        dict  {station_id: [year1, year2, ...]} for stations with files.
        """
        self.cwc_dir.mkdir(parents=True, exist_ok=True)
        available: Dict[str, List[int]] = {}

        # 1. Check for combined files
        combined_exists = False
        combined_years = list(range(self.config["years"]["start"], self.config["years"]["end"] + 1))
        for f in ["cauvery_1991_2020.csv", "cauvery_2021_2025.csv"]:
            if (self.cwc_dir / f).exists():
                combined_exists = True

        if combined_exists:
            for s in self.config["stations"]:
                available[s["id"]] = combined_years

        # 2. Check for individual files and merge
        pattern = re.compile(r"^(.+?)_(\d{4})\.csv$", re.IGNORECASE)
        for f in self.cwc_dir.glob("*.csv"):
            if f.name.lower() in ["cauvery_1991_2020.csv", "cauvery_2021_2025.csv"]:
                continue
            m = pattern.match(f.name)
            if m:
                sid, yr = m.group(1).upper(), int(m.group(2))
                available.setdefault(sid, []).append(yr)

        for sid in available:
            available[sid] = sorted(list(set(available[sid])))

        logger.info(f"CWC: found data for {len(available)} stations: {list(available.keys())}")
        return available

    def report_missing_stations(
        self,
        available: Dict[str, List[int]],
        required_station_ids: List[str],
    ) -> List[str]:
        """
        Log WARNING for each required station with no CSV data.

        Returns list of missing station IDs. NEVER generates fake data.
        """
        missing = []
        for sid in required_station_ids:
            if sid not in available:
                missing.append(sid)
                logger.warning(
                    f"CWC data MISSING for station: {sid}\n"
                    f"  Export from India-WRIS: https://indiawris.gov.in/wris/#/\n"
                    f"  Save as: dataset/raw/cwc/{sid}_{{YYYY}}.csv"
                )
        if not missing:
            logger.info("CWC: all required stations have data files.")
        else:
            logger.warning(f"CWC: {len(missing)} stations without data: {missing}")
        return missing

    # ------------------------------------------------------------------ #
    # Format detection
    # ------------------------------------------------------------------ #

    def _detect_format(self, df_raw: pd.DataFrame) -> str:
        """
        Detect which CWC CSV column format variant is present.

        Returns 'A', 'B', 'C', or 'D' (generic fallback).
        """
        cols_str = " ".join(str(c) for c in df_raw.columns).lower()
        if "water level (m)" in cols_str and "discharge (cumecs)" in cols_str:
            return "A"
        if "water level (m cg)" in cols_str or "cumecs" in cols_str:
            return "B"
        if "wl(m)" in cols_str or "q(cumecs)" in cols_str:
            return "C"
        return "D"

    def _find_col(self, df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
        """Return the first column in *candidates* that exists in *df*."""
        for c in candidates:
            for col in df.columns:
                if str(col).strip().lower() == c.lower():
                    return col
        return None

    # ------------------------------------------------------------------ #
    # Parsing
    # ------------------------------------------------------------------ #

    def parse_station_csv(self, csv_path: Path, station_id: str) -> pd.DataFrame:
        """
        Parse a single CWC station CSV file.

        Handles:
        - Multi-row preambles (skips until header row detected)
        - Encoding variants (UTF-8, Latin-1)
        - IST → UTC conversion (subtract 5:30)
        - Basic range validation (level > 0, discharge >= 0)

        Returns
        -------
        pd.DataFrame  with UTC DatetimeIndex, columns=[level_m, discharge_cumecs].
        Rows with out-of-range values are kept with a quality_flag column (0=good, 1=suspect).
        """
        # Try encodings
        df_raw = None
        for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
            try:
                df_raw = pd.read_csv(csv_path, encoding=enc, header=None, dtype=str)
                break
            except Exception:
                continue
        if df_raw is None:
            logger.error(f"Could not read {csv_path}")
            return pd.DataFrame()

        # Skip preamble rows — find the header row
        header_row = None
        date_keywords = {"date", "time", "sl.no", "date & time", "data acquisition time"}
        for i, row in df_raw.iterrows():
            row_vals = [str(v).strip().lower() for v in row.values]
            if any(kw in " ".join(row_vals) for kw in date_keywords):
                header_row = i
                break

        if header_row is None:
            logger.warning(f"{csv_path.name}: could not find header row, using row 0")
            header_row = 0

        df = pd.read_csv(
            csv_path,
            encoding="latin-1",
            skiprows=header_row,
            dtype=str,
        )
        df.columns = [str(c).strip() for c in df.columns]

        fmt = self._detect_format(df)
        logger.debug(f"{csv_path.name}: format={fmt}")

        # Locate columns
        date_col  = self._find_col(df, self._DATE_COLS)
        time_col  = self._find_col(df, self._TIME_COLS)
        level_col = self._find_col(df, self._LEVEL_COLS)
        disch_col = self._find_col(df, self._DISCH_COLS)

        if date_col is None or level_col is None:
            logger.warning(f"{csv_path.name}: required columns not found (date={date_col}, level={level_col})")
            return pd.DataFrame()

        # Build timestamp column
        if time_col and time_col != date_col:
            ts_str = df[date_col].fillna("") + " " + df[time_col].fillna("00:00")
        else:
            ts_str = df[date_col].fillna("")

        timestamps_ist = pd.to_datetime(ts_str, dayfirst=True, errors="coerce")
        timestamps_utc = timestamps_ist - _IST_OFFSET

        # Parse values
        level_m = pd.to_numeric(df[level_col], errors="coerce")
        if disch_col:
            discharge = pd.to_numeric(df[disch_col], errors="coerce")
        else:
            discharge = pd.Series(np.nan, index=df.index)

        out = pd.DataFrame({
            "timestamp":        timestamps_utc,
            "level_m":          level_m,
            "discharge_cumecs": discharge,
        }).dropna(subset=["timestamp"])

        out["quality_flag"] = 0

        # Validation
        bad_level = out["level_m"] <= 0
        bad_disch = out["discharge_cumecs"] < 0
        n_bad = bad_level.sum() + bad_disch.sum()
        if n_bad > 0:
            logger.warning(
                f"{station_id}/{csv_path.name}: {n_bad} suspect values "
                f"(level<=0: {bad_level.sum()}, discharge<0: {bad_disch.sum()}) — flagged"
            )
            out.loc[bad_level | bad_disch, "quality_flag"] = 1

        out = out.set_index("timestamp").sort_index()
        return out

    # ------------------------------------------------------------------ #
    # Alignment
    # ------------------------------------------------------------------ #

    def align_to_30min_grid(
        self,
        df: pd.DataFrame,
        max_gap_hours: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Resample to a regular 30-minute UTC grid.

        Gaps shorter than *max_gap_hours* are filled by linear interpolation.
        Longer gaps remain NaN. No values are fabricated.

        Parameters
        ----------
        df           : DataFrame with UTC DatetimeIndex.
        max_gap_hours: Maximum gap length to interpolate (default: from config).
        """
        if df.empty:
            return df
        if max_gap_hours is None:
            max_gap_hours = self.max_gap

        max_gap_steps = max_gap_hours * 2  # 30-min steps

        # Resample to 30-min grid
        df_30 = df.resample("30min").mean()

        num_cols = [c for c in df_30.columns if c != "quality_flag"]
        for col in num_cols:
            df_30[col] = df_30[col].interpolate(
                method="linear",
                limit=max_gap_steps,
                limit_direction="forward",
            )

        return df_30

    # ------------------------------------------------------------------ #
    # Load all
    # ------------------------------------------------------------------ #

    def load_all_available(
        self,
        station_ids: List[str],
        years: List[int],
    ) -> Dict[str, pd.DataFrame]:
        """
        Load and combine all available CSV files for the requested stations and years.

        Returns {station_id: aligned_df} only for stations with available data.
        """
        available = self.check_data_availability()
        result: Dict[str, pd.DataFrame] = {}

        # Pre-load combined files if they exist to avoid re-reading for each station
        combined_dfs = []
        for fn in ["cauvery_1991_2020.csv", "cauvery_2021_2025.csv"]:
            fp = self.cwc_dir / fn
            if fp.exists():
                logger.info(f"CWC: reading combined file {fn}...")
                try:
                    df_comb = pd.read_csv(fp, dtype=str)
                    df_comb.columns = [c.replace("'", "").replace('"', '').strip() for c in df_comb.columns]
                    for col in ['Station', 'Data Acquisition Time']:
                        if col in df_comb.columns:
                            df_comb[col] = df_comb[col].astype(str).str.replace("'", "").str.replace('"', '').str.strip()
                    combined_dfs.append(df_comb)
                except Exception as e:
                    logger.error(f"CWC: failed to read {fn}: {e}")

        for sid in station_ids:
            if sid not in available:
                continue

            yr_dfs = []

            # 1. Parse from combined files
            cwc_name = CWC_STATION_MAP.get(sid)
            if cwc_name and combined_dfs:
                for df_comb in combined_dfs:
                    sub_df = df_comb[df_comb['Station'] == cwc_name]
                    if not sub_df.empty:
                        # Find the datetime column and value column
                        date_col  = self._find_col(sub_df, self._DATE_COLS)
                        level_col = self._find_col(sub_df, self._LEVEL_COLS)
                        disch_col = self._find_col(sub_df, self._DISCH_COLS)

                        if date_col and level_col:
                            timestamps_ist = pd.to_datetime(sub_df[date_col], dayfirst=True, errors="coerce")
                            timestamps_utc = timestamps_ist - _IST_OFFSET

                            level_m = pd.to_numeric(sub_df[level_col], errors="coerce")
                            if disch_col:
                                discharge = pd.to_numeric(sub_df[disch_col], errors="coerce")
                            else:
                                discharge = pd.Series(np.nan, index=sub_df.index)

                            parsed_comb = pd.DataFrame({
                                "timestamp":        timestamps_utc,
                                "level_m":          level_m,
                                "discharge_cumecs": discharge,
                            }).dropna(subset=["timestamp"])

                            parsed_comb["quality_flag"] = 0
                            bad_level = parsed_comb["level_m"] <= 0
                            bad_disch = parsed_comb["discharge_cumecs"] < 0
                            parsed_comb.loc[bad_level | bad_disch, "quality_flag"] = 1

                            parsed_comb = parsed_comb.set_index("timestamp").sort_index()
                            yr_dfs.append(parsed_comb)

            # 2. Parse from individual files
            for yr in years:
                csv_path = self.cwc_dir / f"{sid}_{yr}.csv"
                if not csv_path.exists():
                    csv_path = self.cwc_dir / f"{sid.lower()}_{yr}.csv"
                if csv_path.exists():
                    parsed = self.parse_station_csv(csv_path, sid)
                    if not parsed.empty:
                        yr_dfs.append(parsed)

            if yr_dfs:
                combined = pd.concat(yr_dfs).sort_index()
                # filter by requested years
                combined = combined[combined.index.year.isin(years)]
                combined = combined[~combined.index.duplicated(keep="first")]
                aligned  = self.align_to_30min_grid(combined)
                result[sid] = aligned
                logger.info(
                    f"CWC {sid}: {len(aligned):,} 30-min rows "
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
        """Save per-station processed DataFrames as Parquet."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        for sid, df in data.items():
            out = output_dir / f"cwc_{sid}.parquet"
            df.to_parquet(out)
            logger.debug(f"Saved: {out.name} ({len(df):,} rows)")
