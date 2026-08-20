"""
validate_cwc_data.py
Quick audit of CWC gauge and reservoir CSVs placed in dataset/raw/.
Reports: files found, date coverage, missing dates, value ranges.
Run after exporting data from India-WRIS.
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np
import yaml

sys.path.insert(0, str(Path("pipeline")))
config = yaml.safe_load(open("pipeline/config.yaml"))

CWC_DIR = Path("pipeline/dataset/raw/cwc")
RES_DIR = Path("pipeline/dataset/raw/reservoir")

STATIONS   = [s["id"] for s in config["stations"]]
RESERVOIRS = [r["id"] for r in config.get("reservoirs", [])]
YEARS      = list(range(config["years"]["start"], config["years"]["end"] + 1))

DATE_COLS  = ["date","Date","DATE","datetime","Datetime","time","observation_date","Date/Time"]
LEVEL_COLS = ["level_m","gauge_level","water_level","level","stage_m","stage","gauge_height_m"]
FLOW_COLS  = ["discharge_cumecs","discharge","flow","streamflow","Q","q_cumecs","q"]

def detect_col(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None

def audit_csvs(directory, ids, label):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")

    found, missing = [], []
    for sid in ids:
        for year in YEARS:
            fname = f"{sid}_{year}.csv"
            fpath = directory / fname
            if fpath.exists():
                found.append((sid, year, fpath))
            else:
                missing.append(fname)

    print(f"  Expected : {len(ids) * len(YEARS)}")
    print(f"  Found    : {len(found)}")
    print(f"  Missing  : {len(missing)}")
    if missing:
        print(f"\n  Missing files:")
        for m in missing[:20]:
            print(f"    - {m}")
        if len(missing) > 20:
            print(f"    ... and {len(missing)-20} more")

    if not found:
        print(f"\n  ACTION: Export {label} from India-WRIS portal")
        print(f"  Portal : https://indiawris.gov.in/wris/#/")
        return

    print(f"\n  {'Station':<20} {'Year':<6} {'Rows':<8} {'Date Range':<30} {'Issues'}")
    print(f"  {'-'*20} {'-'*6} {'-'*8} {'-'*30} {'-'*20}")

    for sid, year, fpath in found:
        try:
            df = pd.read_csv(fpath, nrows=5000)
            date_col = detect_col(df, DATE_COLS)
            if date_col is None:
                print(f"  {sid:<20} {year:<6} {'?':<8} {'NO DATE COL FOUND':<30} SKIP")
                continue
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
            df = df.dropna(subset=[date_col])

            level_col = detect_col(df, LEVEL_COLS)
            flow_col  = detect_col(df, FLOW_COLS)

            issues = []
            if level_col and (df[level_col] < 0).any():
                issues.append("NEG_LEVEL")
            if flow_col and (df[flow_col] < 0).any():
                issues.append("NEG_FLOW")
            if level_col and (df[level_col] > 50).any():
                issues.append("LEVEL>50m")
            if len(df) < 30:
                issues.append(f"SPARSE({len(df)}rows)")

            date_min = df[date_col].min().strftime("%Y-%m-%d")
            date_max = df[date_col].max().strftime("%Y-%m-%d")
            date_range = f"{date_min} to {date_max}"

            print(f"  {sid:<20} {year:<6} {len(df):<8} {date_range:<30} {', '.join(issues) or 'OK'}")

        except Exception as e:
            print(f"  {sid:<20} {year:<6} {'ERR':<8} {str(e)[:50]}")

# Audit CWC
audit_csvs(CWC_DIR, STATIONS, "CWC GAUGE STATIONS")

# Audit Reservoirs
audit_csvs(RES_DIR, RESERVOIRS, "RESERVOIR DATA")

print("\n" + "="*60)
print("  SUMMARY")
print("="*60)
cwc_total     = len(STATIONS) * len(YEARS)
res_total     = len(RESERVOIRS) * len(YEARS)
cwc_found     = len(list(CWC_DIR.glob("*.csv"))) if CWC_DIR.exists() else 0
res_found     = len(list(RES_DIR.glob("*.csv"))) if RES_DIR.exists() else 0

print(f"  CWC files  : {cwc_found}/{cwc_total}")
print(f"  Reservoir  : {res_found}/{res_total}")
print(f"  Status     : {'READY' if cwc_found == cwc_total and res_found == res_total else 'INCOMPLETE'}")
if cwc_found < cwc_total or res_found < res_total:
    print(f"\n  Next step: Export missing files from https://indiawris.gov.in/wris/#/")
    print(f"  Then run : python pipeline/preprocess.py")
