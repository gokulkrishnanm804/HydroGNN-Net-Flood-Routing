"""
GPM IMERG Output Validation Script
====================================
Compares Parquet outputs from the sequential and optimized GPM downloaders.

Usage:
    python pipeline/validate_gpm_outputs.py \\
        --seq   pipeline/dataset/processed_seq/ \\
        --opt   pipeline/dataset/processed/ \\
        --tol   1e-7

Checks:
    - Identical station IDs (Parquet filenames)
    - Identical row counts per station
    - Identical timestamps (UTC, no timezone drift)
    - Identical precipitation values (within floating-point tolerance)
    - Identical Parquet schema (column names, dtypes)
    - No duplicate timestamps

Exit code: 0 = PASS, 1 = FAIL
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd


# ─── ANSI colours ─────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"

def ok(msg: str)   -> None: print(f"{GREEN}  ✓ {msg}{RESET}")
def fail(msg: str) -> None: print(f"{RED}  ✗ {msg}{RESET}")
def warn(msg: str) -> None: print(f"{YELLOW}  ! {msg}{RESET}")
def hdr(msg: str)  -> None: print(f"\n{'─'*64}\n  {msg}\n{'─'*64}")


def load_parquets(directory: Path) -> Dict[str, pd.DataFrame]:
    """Load all gpm_*.parquet files from directory into a dict keyed by station_id."""
    result = {}
    for p in sorted(directory.glob("gpm_*.parquet")):
        sid = p.stem.replace("gpm_", "")
        df  = pd.read_parquet(p)
        result[sid] = df
    return result


def validate(seq_dir: Path, opt_dir: Path, tol: float) -> bool:
    """
    Run all validation checks.

    Returns True if all checks pass, False otherwise.
    """
    hdr("GPM IMERG Output Validator")
    print(f"  Sequential dir : {seq_dir}")
    print(f"  Optimized dir  : {opt_dir}")
    print(f"  Float tolerance: {tol}")

    passed = 0
    failed = 0

    # ── Load ──────────────────────────────────────────────────────────
    seq = load_parquets(seq_dir)
    opt = load_parquets(opt_dir)

    if not seq:
        fail(f"No gpm_*.parquet files found in sequential dir: {seq_dir}")
        return False
    if not opt:
        fail(f"No gpm_*.parquet files found in optimized dir: {opt_dir}")
        return False

    # ── 1. Station set ─────────────────────────────────────────────────
    hdr("Check 1: Station IDs")
    seq_stations = set(seq.keys())
    opt_stations = set(opt.keys())
    if seq_stations == opt_stations:
        ok(f"Station IDs identical: {sorted(seq_stations)}")
        passed += 1
    else:
        only_seq = seq_stations - opt_stations
        only_opt = opt_stations - seq_stations
        if only_seq: fail(f"In sequential only: {only_seq}")
        if only_opt: warn(f"In optimized only (extra):  {only_opt}")
        failed += 1

    # ── Per-station checks ────────────────────────────────────────────
    for sid in sorted(seq_stations & opt_stations):
        hdr(f"Station: {sid}")
        df_s = seq[sid].copy()
        df_o = opt[sid].copy()

        # Normalise timestamps
        for df in (df_s, df_o):
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
                df.sort_values("timestamp", inplace=True)
                df.reset_index(drop=True, inplace=True)

        # 2. Schema
        hdr(f"  Check 2 [{sid}]: Parquet schema")
        seq_cols = list(df_s.columns)
        opt_cols = list(df_o.columns)
        if seq_cols == opt_cols:
            ok(f"Columns identical: {seq_cols}")
            passed += 1
        else:
            fail(f"Column mismatch — seq: {seq_cols}  opt: {opt_cols}")
            failed += 1

        seq_dtypes = df_s.dtypes.to_dict()
        opt_dtypes = df_o.dtypes.to_dict()
        dtype_ok = all(
            str(seq_dtypes.get(c)) == str(opt_dtypes.get(c))
            for c in seq_cols
        )
        if dtype_ok:
            ok(f"Dtypes identical")
            passed += 1
        else:
            fail(f"Dtype mismatch — seq: {seq_dtypes}  opt: {opt_dtypes}")
            failed += 1

        # 3. Row counts
        hdr(f"  Check 3 [{sid}]: Row counts")
        if len(df_s) == len(df_o):
            ok(f"Row count identical: {len(df_s):,}")
            passed += 1
        else:
            fail(f"Row count mismatch: seq={len(df_s):,}  opt={len(df_o):,}")
            failed += 1
            # Don't check values if lengths differ
            continue

        # 4. Duplicate timestamps
        hdr(f"  Check 4 [{sid}]: Duplicate timestamps")
        dup_s = df_s["timestamp"].duplicated().sum()
        dup_o = df_o["timestamp"].duplicated().sum()
        if dup_s == 0 and dup_o == 0:
            ok("No duplicate timestamps in either output")
            passed += 1
        else:
            if dup_s > 0: fail(f"Sequential has {dup_s} duplicate timestamps")
            if dup_o > 0: fail(f"Optimized has {dup_o} duplicate timestamps")
            failed += 1

        # 5. Timestamps identical
        hdr(f"  Check 5 [{sid}]: Timestamps")
        ts_s = pd.to_datetime(df_s["timestamp"], utc=True)
        ts_o = pd.to_datetime(df_o["timestamp"], utc=True)
        if ts_s.equals(ts_o):
            ok(f"Timestamps identical ({len(ts_s):,} rows)")
            passed += 1
        else:
            n_diff = (ts_s != ts_o).sum()
            fail(f"Timestamps differ at {n_diff} positions")
            failed += 1

        # 6. Precipitation values
        hdr(f"  Check 6 [{sid}]: Precipitation values")
        col = "precipitation_mm_30min"
        if col not in df_s.columns or col not in df_o.columns:
            warn(f"Column '{col}' not in one or both DataFrames — skipping")
        else:
            v_s = df_s[col].values.astype(float)
            v_o = df_o[col].values.astype(float)

            # NaN positions must be identical
            nan_s = np.isnan(v_s)
            nan_o = np.isnan(v_o)
            nan_match = np.all(nan_s == nan_o)

            if not nan_match:
                n_nan_diff = np.sum(nan_s != nan_o)
                fail(f"NaN positions differ at {n_nan_diff} rows")
                failed += 1
            else:
                ok(f"NaN positions identical ({nan_s.sum():,} NaN values)")
                passed += 1

            # Non-NaN values: bit-level comparison with tolerance
            mask = ~nan_s & ~nan_o
            if mask.any():
                max_diff = np.max(np.abs(v_s[mask] - v_o[mask]))
                n_nonnan = mask.sum()
                if max_diff <= tol:
                    ok(
                        f"Values identical (max |diff|={max_diff:.2e}, "
                        f"tol={tol:.0e}, n={n_nonnan:,})"
                    )
                    passed += 1
                else:
                    fail(
                        f"Values differ: max |diff|={max_diff:.6f} > tol={tol:.0e} "
                        f"at {np.sum(np.abs(v_s[mask]-v_o[mask]) > tol):,} positions"
                    )
                    # Show a few differing rows
                    diff_idx = np.where(np.abs(v_s[mask] - v_o[mask]) > tol)[0][:5]
                    for i in diff_idx:
                        ts_val = df_s.iloc[i]["timestamp"]
                        print(f"      row {i}: seq={v_s[i]:.8f}  opt={v_o[i]:.8f}  "
                              f"diff={abs(v_s[i]-v_o[i]):.2e}  ts={ts_val}")
                    failed += 1
            else:
                ok("All non-NaN values checked (none present)")
                passed += 1

    # ── Summary ───────────────────────────────────────────────────────
    hdr("VALIDATION SUMMARY")
    total = passed + failed
    pct   = passed / max(total, 1) * 100
    print(f"  Checks passed: {passed}/{total}  ({pct:.0f}%)")
    if failed == 0:
        print(f"\n{GREEN}  ✓ ALL CHECKS PASSED — outputs are scientifically identical{RESET}\n")
        return True
    else:
        print(f"\n{RED}  ✗ {failed} CHECKS FAILED — outputs differ{RESET}\n")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate GPM IMERG Parquet outputs")
    parser.add_argument(
        "--seq",
        required=True,
        help="Directory containing sequential downloader Parquet outputs",
    )
    parser.add_argument(
        "--opt",
        required=True,
        help="Directory containing optimized downloader Parquet outputs",
    )
    parser.add_argument(
        "--tol",
        type=float,
        default=1e-7,
        help="Floating-point tolerance for value comparison (default: 1e-7)",
    )
    args = parser.parse_args()

    seq_dir = Path(args.seq)
    opt_dir = Path(args.opt)

    for d in (seq_dir, opt_dir):
        if not d.exists():
            print(f"{RED}Error: directory does not exist: {d}{RESET}")
            sys.exit(1)

    ok_result = validate(seq_dir, opt_dir, args.tol)
    sys.exit(0 if ok_result else 1)


if __name__ == "__main__":
    main()
