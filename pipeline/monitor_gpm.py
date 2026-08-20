"""
GPM IMERG Download + Extraction Monitor (corrected)
Shows: HDF5 files on disk (pending extraction), extracted Parquet sizes, disk usage.
"""
from pathlib import Path
import sys

gpm_raw  = Path("pipeline/dataset/raw/gpm")
gpm_proc = Path("pipeline/dataset/processed")

TOTAL_YEARS    = 6
SLOTS_PER_YEAR = 48 * 365          # ~17,520 (ignoring leap years for estimate)
TOTAL_SLOTS    = TOTAL_YEARS * 48 * 365   # ~105,120

print("=" * 64)
print("  GPM IMERG 2018-2023  |  Download + Extraction Monitor")
print("=" * 64)

# --- Raw HDF5 on disk (pending extraction) ---
hdf5_files = list(gpm_raw.rglob("*.HDF5"))
hdf5_size  = sum(f.stat().st_size for f in hdf5_files) / 1e6
print(f"\n[RAW] HDF5 on disk (pending extraction)")
print(f"  Files  : {len(hdf5_files):>7,}")
print(f"  Size   : {hdf5_size/1024:>7.2f} GB")

# --- Per-year HDF5 breakdown ---
print(f"\n  Year    HDF5 on disk   Est. slots processed")
for year in range(2018, 2024):
    yr_dir   = gpm_raw / str(year)
    yr_files = list(yr_dir.rglob("*.HDF5")) if yr_dir.exists() else []
    yr_mb    = sum(f.stat().st_size for f in yr_files) / 1e6
    print(f"  {year}    {len(yr_files):>7,} files   {yr_mb:>8.0f} MB")

# --- Extracted Parquet files ---
print(f"\n[PROCESSED] Extracted Parquet files")
parquet_files = list(gpm_proc.glob("gpm_*.parquet")) if gpm_proc.exists() else []
if parquet_files:
    total_rows = 0
    for pf in sorted(parquet_files):
        try:
            import pandas as pd
            df = pd.read_parquet(pf)
            rows = len(df)
            total_rows += rows
            date_min = df["timestamp"].min() if "timestamp" in df.columns else "?"
            date_max = df["timestamp"].max() if "timestamp" in df.columns else "?"
            print(f"  {pf.name:<35} {rows:>8,} rows  {date_min} → {date_max}")
        except Exception as e:
            print(f"  {pf.name:<35} ERROR: {e}")
    print(f"\n  Total extracted rows: {total_rows:,}")
    # Each station should have 48 rows/day × ~2190 days = ~105,120 rows when complete
    pct = total_rows / (TOTAL_SLOTS * len(parquet_files)) * 100 if parquet_files else 0
    print(f"  Extraction progress : {pct:.1f}% complete")
else:
    print("  No parquet files yet — extraction completes after first full year download")
    print("  (GPM downloads one year fully, then extracts all at once)")

print(f"\n{'=' * 64}")
