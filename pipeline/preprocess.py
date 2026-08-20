"""
HydroGNN-Net Data Preprocessing Orchestrator
=============================================
Validates and preprocesses all downloaded raw data into aligned, 30-minute
time series suitable for feature engineering and GNN training.

Prerequisite: python pipeline/download_all.py

Usage
-----
    python pipeline/preprocess.py
    python pipeline/preprocess.py --config pipeline/config.yaml
    python pipeline/preprocess.py --skip-validation   # Skip HTML report
    python pipeline/preprocess.py --station METTUR_DAM  # Process one station

Outputs
-------
    dataset/processed/gpm_processed_{station_id}.parquet
    dataset/processed/era5_processed_{station_id}.parquet
    dataset/processed/cwc_{station_id}.parquet
    dataset/processed/reservoir_{reservoir_id}.parquet
    dataset/processed/terrain_attributes.csv
    dataset/logs/validation_report.html     ← Open in browser to inspect data quality
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

import yaml
import pandas as pd
import numpy as np

from src.utils.logger import get_logger, log_separator
from src.utils.cache import DataSourceUnavailable

logger = get_logger("preprocess")


def load_config(config_path: Path) -> dict:
    with open(config_path) as fh:
        return yaml.safe_load(fh)


def resolve_paths(config: dict, project_root: Path) -> dict:
    for key in config["paths"]:
        p = Path(config["paths"][key])
        if not p.is_absolute():
            config["paths"][key] = str(project_root / "pipeline" / p)
    return config


# ─────────────────────────────────────────────────────────────────────────────
# Validation report generator (standalone — no DataValidator dependency)
# ─────────────────────────────────────────────────────────────────────────────

def _html_badge(status: str) -> str:
    colours = {"OK": "#22c55e", "WARNING": "#f59e0b", "CRITICAL": "#ef4444", "MISSING": "#6b7280"}
    bg = colours.get(status, "#6b7280")
    return f'<span style="background:{bg};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px">{status}</span>'


def generate_validation_report(
    summaries: list,
    output_path: Path,
) -> None:
    """
    Write a standalone HTML validation report.

    Parameters
    ----------
    summaries : list of dicts with keys:
                source, station_id, status, total_rows, missing_pct, notes
    output_path : Where to write the HTML file.
    """
    from datetime import datetime, timezone

    rows_html = ""
    for s in summaries:
        badge = _html_badge(s["status"])
        missing = f"{s.get('missing_pct', 0):.1f}%"
        rows_html += (
            f"<tr>"
            f"<td>{s['source']}</td>"
            f"<td>{s['station_id']}</td>"
            f"<td>{badge}</td>"
            f"<td>{s.get('total_rows', 0):,}</td>"
            f"<td>{missing}</td>"
            f"<td>{s.get('notes', '')}</td>"
            f"</tr>\n"
        )

    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>HydroGNN-Net Data Validation Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background:#0f172a;color:#e2e8f0;margin:0;padding:24px }}
  h1   {{ color:#38bdf8;margin-bottom:4px }}
  p.sub {{ color:#94a3b8;margin-top:0 }}
  table {{ width:100%;border-collapse:collapse;background:#1e293b;border-radius:8px;overflow:hidden }}
  th   {{ background:#0f172a;color:#94a3b8;text-align:left;padding:10px 14px;font-size:13px;text-transform:uppercase;letter-spacing:.05em }}
  td   {{ padding:10px 14px;border-bottom:1px solid #334155;font-size:14px }}
  tr:last-child td {{ border-bottom:none }}
  tr:hover td {{ background:#273449 }}
  footer {{ color:#475569;font-size:12px;margin-top:16px }}
</style>
</head>
<body>
<h1>🌊 HydroGNN-Net Data Validation Report</h1>
<p class="sub">Cauvery Basin, Tamil Nadu, India — Generated: {now}</p>
<table>
<thead>
  <tr>
    <th>Source</th><th>Station / Reservoir</th><th>Status</th>
    <th>Rows</th><th>Missing%</th><th>Notes</th>
  </tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
<footer>HydroGNN-Net IEEE Final Year Project — All data from official CWC/NASA/Copernicus sources</footer>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    logger.info(f"Validation report: {output_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Processing functions
# ─────────────────────────────────────────────────────────────────────────────

def process_gpm(config: dict) -> list:
    """Process GPM IMERG station extracts → rolling accumulations."""
    from src.features.rolling_rainfall import compute_rolling_rainfall

    proc_dir = Path(config["paths"]["processed_dir"])
    summaries = []
    windows   = config["features"]["rolling_windows_hours"]

    for sid in [s["id"] for s in config["stations"]]:
        parquet_in = proc_dir / f"gpm_{sid}.parquet"
        if not parquet_in.exists():
            summaries.append({
                "source": "GPM", "station_id": sid, "status": "MISSING",
                "total_rows": 0, "missing_pct": 100,
                "notes": f"File not found: {parquet_in.name}",
            })
            continue
        try:
            df = pd.read_parquet(parquet_in)
            df = compute_rolling_rainfall(df, windows_hours=windows)
            missing_pct = df["precipitation_mm_30min"].isna().mean() * 100
            out_path = proc_dir / f"gpm_processed_{sid}.parquet"
            df.to_parquet(out_path, index=False)
            # Use the last configured window for the 'max accumulation' note
            max_col = f"rainfall_{windows[-1]}h" if windows else None
            if max_col and max_col in df.columns:
                rain_note = f"Max {windows[-1]}h: {df[max_col].max():.1f}mm"
            else:
                rain_note = f"{len(df)} rows saved"
            summaries.append({
                "source": "GPM", "station_id": sid,
                "status": "WARNING" if missing_pct > 10 else "OK",
                "total_rows": len(df),
                "missing_pct": missing_pct,
                "notes": rain_note,
            })
        except Exception as exc:
            summaries.append({
                "source": "GPM", "station_id": sid, "status": "CRITICAL",
                "total_rows": 0, "missing_pct": 100, "notes": str(exc)[:80],
            })
    return summaries


def process_cwc(config: dict) -> list:
    """Load and validate CWC station data."""
    from src.downloaders.cwc import CWCDataParser

    raw_dir  = Path(config["paths"]["raw_dir"])
    proc_dir = Path(config["paths"]["processed_dir"])
    parser   = CWCDataParser(raw_dir, config)
    years    = list(range(config["years"]["start"], config["years"]["end"] + 1))
    station_ids = [s["id"] for s in config["stations"]]
    data     = parser.load_all_available(station_ids, years)
    parser.save_processed(data, proc_dir)

    summaries = []
    for sid in station_ids:
        if sid in data:
            df          = data[sid]
            missing_pct = df["level_m"].isna().mean() * 100
            summaries.append({
                "source": "CWC", "station_id": sid,
                "status": "WARNING" if missing_pct > 10 else "OK",
                "total_rows": len(df),
                "missing_pct": missing_pct,
                "notes": f"Level range: {df['level_m'].min():.1f}–{df['level_m'].max():.1f} m",
            })
        else:
            summaries.append({
                "source": "CWC", "station_id": sid, "status": "MISSING",
                "total_rows": 0, "missing_pct": 100,
                "notes": "No CSV files found in dataset/raw/cwc/",
            })
    return summaries


def process_reservoir(config: dict) -> list:
    """Load and validate reservoir data."""
    from src.downloaders.reservoir import ReservoirDataParser

    raw_dir  = Path(config["paths"]["raw_dir"])
    proc_dir = Path(config["paths"]["processed_dir"])
    parser   = ReservoirDataParser(raw_dir, config)
    years    = list(range(config["years"]["start"], config["years"]["end"] + 1))
    res_ids  = [r["id"] for r in config["reservoirs"]]
    data     = parser.load_all_available(res_ids, years)
    parser.save_processed(data, proc_dir)

    summaries = []
    for rid in res_ids:
        if rid in data:
            df          = data[rid]
            missing_pct = df["storage_pct"].isna().mean() * 100
            summaries.append({
                "source": "Reservoir", "station_id": rid,
                "status": "WARNING" if missing_pct > 10 else "OK",
                "total_rows": len(df),
                "missing_pct": missing_pct,
                "notes": f"Storage: {df['storage_pct'].min():.0f}–{df['storage_pct'].max():.0f}%",
            })
        else:
            summaries.append({
                "source": "Reservoir", "station_id": rid, "status": "MISSING",
                "total_rows": 0, "missing_pct": 100,
                "notes": "No CSV files found in dataset/raw/reservoir/",
            })
    return summaries


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="HydroGNN-Net Preprocessing")
    parser.add_argument("--config", default="pipeline/config.yaml")
    parser.add_argument("--skip-validation", action="store_true")
    args = parser.parse_args()

    project_root = PIPELINE_DIR.parent
    config_path  = Path(args.config)
    if not config_path.is_absolute():
        config_path = project_root / config_path
    config       = resolve_paths(load_config(config_path), project_root)

    logs_dir = Path(config["paths"]["logs_dir"])
    logs_dir.mkdir(parents=True, exist_ok=True)
    proc_dir = Path(config["paths"]["processed_dir"])
    proc_dir.mkdir(parents=True, exist_ok=True)

    all_summaries = []

    log_separator(logger, "Step 1: GPM IMERG Rolling Accumulations")
    all_summaries.extend(process_gpm(config))

    log_separator(logger, "Step 2: CWC River Gauge Data")
    all_summaries.extend(process_cwc(config))

    log_separator(logger, "Step 3: Reservoir Data")
    all_summaries.extend(process_reservoir(config))

    log_separator(logger, "Step 4: ERA5 Reanalysis Preprocessing")
    try:
        from src.downloaders.era5 import ERA5Downloader
        from src.utils.cache import CacheManager
        from src.utils.logger import DownloadLogger
        cache   = CacheManager(Path(config["paths"]["logs_dir"]) / "cache")
        dl_log  = DownloadLogger(Path(config["paths"]["logs_dir"]) / "download_log.csv")
        era5_dl = ERA5Downloader(cache, dl_log, config)
        years   = list(range(config["years"]["start"], config["years"]["end"] + 1))
        era5_summaries = era5_dl.preprocess_all_years(
            years,
            raw_dir=Path(config["paths"]["raw_dir"]) / "era5",
            proc_dir=Path(config["paths"]["processed_dir"]),
            station_ids=[s["id"] for s in config["stations"]],
            station_coords=[(s["lat"], s["lon"]) for s in config["stations"]],
        )
        all_summaries.extend(era5_summaries)
    except DataSourceUnavailable as e:
        logger.warning(f"ERA5 not available (CDS credentials required): {e}")
    except AttributeError:
        logger.warning(
            "ERA5 preprocess_all_years() not implemented — skipping ERA5 validation.\n"
            "ERA5 data will be used as-is if parquet files exist in processed_dir."
        )
    except Exception as e:
        logger.warning(f"ERA5 preprocessing step failed: {e}")

    # ── Summary ───────────────────────────────────────────────────────────
    log_separator(logger, "Preprocessing Summary")
    ok  = sum(1 for s in all_summaries if s["status"] == "OK")
    mis = sum(1 for s in all_summaries if s["status"] == "MISSING")
    cri = sum(1 for s in all_summaries if s["status"] == "CRITICAL")
    war = sum(1 for s in all_summaries if s["status"] == "WARNING")
    logger.info(f"OK: {ok}  |  WARNING: {war}  |  MISSING: {mis}  |  CRITICAL: {cri}")

    if not args.skip_validation:
        report_path = logs_dir / "validation_report.html"
        generate_validation_report(all_summaries, report_path)
        logger.info(f"Open validation report in browser: {report_path}")

    if cri > 0:
        logger.error("CRITICAL errors found — fix before running create_dataset.py")
    elif mis > 0:
        logger.warning(
            f"{mis} sources MISSING — pipeline will proceed with available data.\n"
            "Missing CWC/reservoir data: export CSVs from https://indiawris.gov.in"
        )
    else:
        logger.info("All sources OK. Next: python pipeline/create_dataset.py")


if __name__ == "__main__":
    main()
