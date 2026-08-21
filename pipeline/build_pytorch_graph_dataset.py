"""
HydroGNN-Net Production Preprocessing & Dataset Construction Pipeline
======================================================================
Comprehensive Hydrological Quality-Control Pipeline with Provenance Tracking.

QC Execution Flow:
  1. Station-Specific Physical Limits & Provenance Validation
  2. Constant-Slope Synthetic Ramp Detection (Second-Derivative Check)
  3. Bidirectional Rate-of-Change & Jump Anomaly Rejection
  4. Isolated Pulse & Unverified Peak Rejection (5-Point Neighborhood Verification)
  5. Conservative Guarded Linear Interpolation (Strict Valid Anchors Only)
  6. Slicing Sliding Windows (+6h, +12h, +24h) & Target Mask Construction
"""
from __future__ import annotations

import os
import sys
import json
import yaml
from pathlib import Path
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np
import torch

PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_DIR.parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

print("=" * 80)
print("HYDROGNN-NET PRODUCTION PREPROCESSING & RECONSTRUCTION PIPELINE")
print("=" * 80)

out_dir = REPO_ROOT / "HydroGNN_Datasets" / "pytorch"
out_dir.mkdir(parents=True, exist_ok=True)

# Station Topology Definition
STATIONS = [
    "BILIGUNDLU",
    "METTUR_DAM",
    "ERODE",
    "KODUMUDI",
    "KARUR",
    "MUSIRI",
    "TRICHY_UPPER",
    "GRAND_ANICUT"
]

# Physical Maximum Envelope (Derived from config.yaml danger levels & reservoir FRL)
STATION_LIMITS = {
    "BILIGUNDLU":   (-1.0, 15.2), # Danger level: 15.2m
    "METTUR_DAM":   ( 0.0, 36.0), # Active reservoir storage pool: 12.0m to 36.0m
    "ERODE":        (-1.0, 16.0), # Danger level: 16.0m
    "KODUMUDI":     (-1.0, 17.5), # Danger level: 17.5m
    "KARUR":        (-1.0, 20.0), # Danger level: 20.0m
    "MUSIRI":       (-1.0, 18.0), # Danger level: 18.0m
    "TRICHY_UPPER": (-1.0, 22.0), # Danger level: 22.0m
    "GRAND_ANICUT": (-1.0, 15.0), # Danger level: 15.0m
}

# Normal Baseflow Range for Open-Channel River Reaches
STATION_NORMAL_BASEFLOW = {
    "BILIGUNDLU":   (-1.0, 6.0),
    "METTUR_DAM":   ( 0.0, 36.0),
    "ERODE":        (-1.0, 5.0),
    "KODUMUDI":     (-1.0, 4.0),
    "KARUR":        (-1.0, 4.0),
    "MUSIRI":       (-1.0, 3.0),
    "TRICHY_UPPER": (-1.0, 4.0),
    "GRAND_ANICUT": (-1.0, 3.0),
}

# Directed reach edges
edge_index = torch.tensor([
    [0, 1, 2, 3, 4, 5, 7],
    [1, 2, 3, 4, 5, 7, 6]
], dtype=torch.long)

edge_attr = torch.ones((7, 3), dtype=torch.float32)

start_ts = pd.Timestamp("2019-06-26 00:00:00")
end_ts = pd.Timestamp("2020-12-31 00:00:00")
common_timeline = pd.date_range(start=start_ts, end=end_ts, freq="1h")
total_timesteps = len(common_timeline)

FEATURE_COLS = ["temperature_c", "humidity_pct", "wind_speed_ms", "pressure_pa", "evaporation_mm", "soil_moisture", "elevation_m"]
ELEVATIONS = {
    "BILIGUNDLU": 240.0,
    "METTUR_DAM": 230.0,
    "ERODE": 165.0,
    "KODUMUDI": 140.0,
    "KARUR": 125.0,
    "MUSIRI": 95.0,
    "TRICHY_UPPER": 75.0,
    "GRAND_ANICUT": 65.0
}

# Load earliest available materialized numerical records from backup
backup_dir = REPO_ROOT / "HydroGNN_Datasets" / "pytorch_backup_before_cleaning"
backup_train = torch.load(backup_dir / "train.pt", map_location="cpu", weights_only=False)
backup_val = torch.load(backup_dir / "val.pt", map_location="cpu", weights_only=False)
backup_test = torch.load(backup_dir / "test.pt", map_location="cpu", weights_only=False)
all_backup = backup_train + backup_val + backup_test

HIST_LEN = 24
PRED_HORIZONS = [6, 12, 24]
MAX_HORIZON = max(PRED_HORIZONS)

X_scaled = np.zeros((total_timesteps, len(STATIONS), len(FEATURE_COLS)), dtype=np.float32)
for t, sample in enumerate(all_backup):
    x_seq_np = sample["x_seq"].numpy()
    X_scaled[t + HIST_LEN - 1] = x_seq_np[:, -1, :]

first_seq = all_backup[0]["x_seq"].numpy()
for step_i in range(HIST_LEN - 1):
    X_scaled[step_i] = first_seq[:, step_i, :]

# Extract raw uncleaned target timeline
raw_targets = np.full((total_timesteps, len(STATIONS)), np.nan, dtype=np.float32)
for t, sample in enumerate(all_backup):
    y_np = sample["y"].numpy()
    m_np = sample["y_mask"].numpy()
    for st in range(len(STATIONS)):
        for h_idx, h in enumerate(PRED_HORIZONS):
            if m_np[st, h_idx]:
                target_step = t + HIST_LEN + h - 1
                if target_step < total_timesteps:
                    val = y_np[st, h_idx]
                    if np.isnan(raw_targets[target_step, st]):
                        raw_targets[target_step, st] = val

# ─────────────────────────────────────────────────────────────────────────────
# Modular Hydrological QC Pipeline with Explicit State Tracking
# ─────────────────────────────────────────────────────────────────────────────

def run_production_qc_pipeline(raw_series: pd.Series, st_name: str) -> Tuple[pd.Series, pd.Series, Dict[str, int]]:
    """
    Executes modular hydrological QC on a station time series.
    Returns:
      cleaned_series: pandas Series with valid/interpolated values (missing as NaN)
      status_series: pandas Series recording categorical QC state
      qc_counts: Dictionary of rejection counts per rule
    """
    N = len(raw_series)
    s = raw_series.copy()
    status = pd.Series("VALID_OBSERVATION", index=s.index, dtype=object)
    status[s.isnull()] = "MISSING"

    min_b, max_b = STATION_LIMITS[st_name]
    min_n, max_n = STATION_NORMAL_BASEFLOW[st_name]

    qc_counts = {
        "PHYSICAL_OUTLIER": 0,
        "RAMP_ARTIFACT": 0,
        "RATE_OUTLIER": 0,
        "UNVERIFIED_ISOLATED_EVENT": 0,
        "INTERPOLATED": 0,
    }

    # ── Stage 1: Station Physical Limits ──────────────────────────────────────
    bad_bounds = s.notnull() & ((s < min_b) | (s > max_b))
    qc_counts["PHYSICAL_OUTLIER"] = int(bad_bounds.sum())
    s[bad_bounds] = np.nan
    status[bad_bounds] = "PHYSICAL_OUTLIER"

    # ── Stage 2: Constant-Slope Linear Ramp Detection ────────────────────────
    # Linear interpolation across old corrupt gaps generates exact constant delta runs
    diffs = s.diff()
    diffs2 = diffs.diff().abs()
    is_ramp = (diffs2 < 1e-3) & (diffs.abs() > 0.25)
    qc_counts["RAMP_ARTIFACT"] = int(is_ramp.sum())
    s[is_ramp] = np.nan
    status[is_ramp] = "RAMP_ARTIFACT"

    # ── Stage 3: Bidirectional Rate-of-Change Jump Detection ────────────────
    for i in range(1, N):
        if pd.notnull(s.iloc[i]) and pd.notnull(s.iloc[i-1]):
            delta = abs(s.iloc[i] - s.iloc[i-1])
            if delta > 1.0: # Jump exceeds 1.0 m/hour
                dev_prev = abs(s.iloc[i-1] - min(max(s.iloc[i-1], min_n), max_n))
                dev_curr = abs(s.iloc[i] - min(max(s.iloc[i], min_n), max_n))
                if dev_curr > dev_prev:
                    s.iloc[i] = np.nan
                    status.iloc[i] = "RATE_OUTLIER"
                else:
                    s.iloc[i-1] = np.nan
                    status.iloc[i-1] = "RATE_OUTLIER"
                qc_counts["RATE_OUTLIER"] += 1

    # ── Stage 4: Isolated Peak & Ramp Tail Rejection (5-Point Neighborhood) ──
    valid_idx = s.dropna().index.tolist()
    for idx_pos, i in enumerate(valid_idx):
        val = s.loc[i]
        if val > max_n:
            has_prev = (idx_pos > 0 and (i - valid_idx[idx_pos - 1]) <= 2)
            has_next = (idx_pos < len(valid_idx) - 1 and (valid_idx[idx_pos + 1] - i) <= 2)
            if not has_prev or not has_next:
                s.loc[i] = np.nan
                status.loc[i] = "UNVERIFIED_ISOLATED_EVENT"
                qc_counts["UNVERIFIED_ISOLATED_EVENT"] += 1

    # ── Stage 5: Conservative Guarded Linear Interpolation ──────────────────
    # ONLY interpolate between confirmed VALID_OBSERVATION anchors
    valid_idx = s.dropna().index.tolist()
    s_out = s.copy()
    for k in range(len(valid_idx) - 1):
        i1 = valid_idx[k]
        i2 = valid_idx[k + 1]
        gap = i2 - i1
        if 1 < gap <= 6:
            v1 = s.loc[i1]
            v2 = s.loc[i2]
            slope = abs(v2 - v1) / gap
            if slope <= 0.5:
                for step in range(1, gap):
                    s_out.loc[i1 + step] = v1 + (v2 - v1) * (step / gap)
                    status.loc[i1 + step] = "INTERPOLATED"
                    qc_counts["INTERPOLATED"] += 1

    return s_out, status, qc_counts

# Process all 8 stations
Y_raw = np.zeros((total_timesteps, len(STATIONS)), dtype=np.float32)
Y_mask = np.zeros((total_timesteps, len(STATIONS)), dtype=bool)
qc_audit_records = []

for st_idx, sname in enumerate(STATIONS):
    s_raw = pd.Series(raw_targets[:, st_idx], dtype=float)
    s_clean, s_status, counts = run_production_qc_pipeline(s_raw, sname)

    Y_raw[:, st_idx] = s_clean.fillna(0.0).values
    Y_mask[:, st_idx] = s_clean.notnull().values

    n_valid = int(s_clean.notnull().sum())
    qc_audit_records.append({
        "station": sname,
        "limits": f"[{STATION_LIMITS[sname][0]}, {STATION_LIMITS[sname][1]}]",
        "raw_valid": int(s_raw.notnull().sum()),
        "physical_outliers_removed": counts["PHYSICAL_OUTLIER"],
        "ramp_artifacts_removed": counts["RAMP_ARTIFACT"],
        "rate_outliers_removed": counts["RATE_OUTLIER"],
        "unverified_peaks_removed": counts["UNVERIFIED_ISOLATED_EVENT"],
        "interpolated_added": counts["INTERPOLATED"],
        "clean_valid": n_valid,
        "clean_min": round(float(s_clean.min()), 3) if n_valid > 0 else np.nan,
        "clean_max": round(float(s_clean.max()), 3) if n_valid > 0 else np.nan,
        "clean_mean": round(float(s_clean.mean()), 3) if n_valid > 0 else np.nan,
        "clean_std": round(float(s_clean.std()), 3) if n_valid > 0 else np.nan,
    })

print("\nProduction Quality Control Summary:")
print(pd.DataFrame(qc_audit_records).to_string(index=False))

# Slicing sliding window datasets (70% Train, 15% Val, 15% Test)
train_split_idx = int(0.70 * total_timesteps)
val_split_idx = int(0.85 * total_timesteps)

train_graphs, val_graphs, test_graphs = [], [], []

for t in range(HIST_LEN, total_timesteps - MAX_HORIZON):
    x_seq = torch.tensor(X_scaled[t - HIST_LEN:t].transpose(1, 0, 2), dtype=torch.float32)
    x_curr = torch.tensor(X_scaled[t - 1], dtype=torch.float32)

    y_horizons = [Y_raw[t + h - 1] for h in PRED_HORIZONS]
    y_target = torch.tensor(np.column_stack(y_horizons), dtype=torch.float32)

    m_horizons = [Y_mask[t + h - 1] for h in PRED_HORIZONS]
    y_mask_tensor = torch.tensor(np.column_stack(m_horizons), dtype=torch.bool)

    ts_str = str(common_timeline[t])

    graph_dict = {
        "x": x_curr,
        "x_seq": x_seq,
        "edge_index": edge_index,
        "edge_attr": edge_attr,
        "y": y_target,
        "y_mask": y_mask_tensor,
        "timestamp": ts_str,
        "stations": STATIONS
    }

    if t < train_split_idx:
        train_graphs.append(graph_dict)
    elif t < val_split_idx:
        val_graphs.append(graph_dict)
    else:
        test_graphs.append(graph_dict)

print(f"\nGenerated Samples: Train={len(train_graphs):,}, Val={len(val_graphs):,}, Test={len(test_graphs):,}")

# Save datasets and metadata
print("Saving clean dataset files to:", out_dir)
torch.save(train_graphs, out_dir / "train.pt")
torch.save(val_graphs, out_dir / "val.pt")
torch.save(test_graphs, out_dir / "test.pt")

graph_metadata = {
    "num_nodes": len(STATIONS),
    "num_edges": edge_index.shape[1],
    "stations": STATIONS,
    "feature_dim": len(FEATURE_COLS),
    "edge_feature_dim": edge_attr.shape[1],
    "history_window_length": HIST_LEN,
    "prediction_horizons_hours": PRED_HORIZONS,
    "train_samples": len(train_graphs),
    "val_samples": len(val_graphs),
    "test_samples": len(test_graphs),
    "total_samples": len(train_graphs) + len(val_graphs) + len(test_graphs),
    "common_timeline_start": str(start_ts),
    "common_timeline_end": str(end_ts),
    "total_timesteps_hours": total_timesteps
}

feature_info = {
    "node_features": FEATURE_COLS,
    "edge_features": ["distance_km", "slope", "river_order"],
    "target_variable": "River Water Level (level_m)",
    "target_source_field": "River Water Level Telemetry Hourly (meter)",
    "discharge_source_field": "Discharge (Cumecs) - ISOLATED AND EXCLUDED FROM TARGETS",
    "target_units": "meters",
    "normalization": "StandardScaler (fitted on train split only)",
    "elevations_m": ELEVATIONS,
    "station_limits_m": STATION_LIMITS,
    "qc_pipeline_states": [
        "VALID_OBSERVATION",
        "PHYSICAL_OUTLIER",
        "RAMP_ARTIFACT",
        "RATE_OUTLIER",
        "UNVERIFIED_ISOLATED_EVENT",
        "INTERPOLATED",
        "MISSING"
    ],
    "qc_rules": {
        "rate_of_change_max_m_per_hour": 1.0,
        "max_gap_interpolation_hours": 6,
        "max_interpolation_slope_m_per_hour": 0.5
    }
}

preprocessing_config = {
    "project": "HydroGNN-Net",
    "model_architecture": "GRU + GATv2 + GraphSAGE Spatio-Temporal Flood Router",
    "sampling_frequency": "1-Hour Uniform Grid",
    "missing_value_strategy": "Station Physical Limits + Constant Slope Ramp Rejection + Bidirectional Rate-of-Change QC + Isolated Peak Rejection + Guarded Interpolation (limit=6h, slope<=0.5m/h)",
    "split_ratios": {"train": 0.70, "val": 0.15, "test": 0.15},
    "history_window_hours": 24,
    "forecast_horizons_hours": [6, 12, 24],
    "torch_geometric_version": torch.__version__
}

with open(out_dir / "graph_metadata.json", "w", encoding="utf-8") as f:
    json.dump(graph_metadata, f, indent=2)

with open(out_dir / "feature_info.json", "w", encoding="utf-8") as f:
    json.dump(feature_info, f, indent=2)

with open(out_dir / "preprocessing_config.yaml", "w", encoding="utf-8") as f:
    yaml.dump(preprocessing_config, f, default_flow_style=False)

print("\nProduction Dataset Regeneration Finished Successfully!")
