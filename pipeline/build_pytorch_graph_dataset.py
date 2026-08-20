import os, sys, glob, json, pickle, yaml
import pandas as pd
import numpy as np
import torch
from sklearn.preprocessing import StandardScaler
from datetime import datetime

print("Starting HydroGNN-Net PyTorch Geometric Graph Dataset Construction Pipeline...")

# Paths
root_dir = r"c:\Users\gokul\Downloads\new_project"
out_dir = os.path.join(root_dir, "processed_dataset")
os.makedirs(out_dir, exist_ok=True)

# Station Order & Graph Topology Definition
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

station_to_idx = {name: idx for idx, name in enumerate(STATIONS)}

# Load Nodes & Edges
nodes_csv = os.path.join(root_dir, "pipeline", "dataset", "graphs", "nodes.csv")
edges_csv = os.path.join(root_dir, "pipeline", "dataset", "graphs", "edges.csv")
edge_attrs_csv = os.path.join(root_dir, "pipeline", "dataset", "graphs", "edge_attributes.csv")

nodes_df = pd.read_csv(nodes_csv)
edges_df = pd.read_csv(edges_csv)
edge_attrs_df = pd.read_csv(edge_attrs_csv) if os.path.exists(edge_attrs_csv) else None

# Build edge_index tensor (2, E)
src_indices = [station_to_idx[src] for src in edges_df["src_id"]]
dst_indices = [station_to_idx[dst] for dst in edges_df["dst_id"]]
edge_index = torch.tensor([src_indices, dst_indices], dtype=torch.long)

# Build edge_attr tensor (E, F_edge)
if edge_attrs_df is not None:
    # Scale distance, slope, order
    dist = edge_attrs_df["distance_km"].values if "distance_km" in edge_attrs_df else np.ones(len(edges_df))
    slope = edge_attrs_df["slope"].values if "slope" in edge_attrs_df else np.ones(len(edges_df))
    order = edge_attrs_df["river_order"].values if "river_order" in edge_attrs_df else np.ones(len(edges_df))
    edge_attr_mat = np.column_stack([dist, slope, order])
else:
    edge_attr_mat = np.ones((len(edges_df), 3))

edge_attr = torch.tensor(edge_attr_mat, dtype=torch.float32)

print(f"Graph Topology Built: {len(STATIONS)} nodes, {edge_index.shape[1]} directed edges.")

# Step 2 & 4: Load and Align Station Data (Hourly Grid from 2019-06-26 to 2020-12-31)
# Create a common hourly datetime range across overlapping period
start_ts = pd.Timestamp("2019-06-26 00:00:00")
end_ts = pd.Timestamp("2020-12-31 00:00:00")
common_timeline = pd.date_range(start=start_ts, end=end_ts, freq="1h")
total_timesteps = len(common_timeline)

print(f"Common Hourly Timeline: {start_ts} to {end_ts} ({total_timesteps} hourly steps)")

# Feature Columns (7 Features)
FEATURE_COLS = ["temperature_c", "humidity_pct", "wind_speed_ms", "pressure_pa", "evaporation_mm", "soil_moisture", "elevation_m"]
TARGET_COL = "level_m"

# Elevation mapping per node (meters above sea level)
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

# Matrices to store full timeline data: Shape (T, N, F) for features, Shape (T, N) for target
X_raw = np.zeros((total_timesteps, len(STATIONS), len(FEATURE_COLS)), dtype=np.float32)
Y_raw = np.zeros((total_timesteps, len(STATIONS)), dtype=np.float32)
Y_mask = np.zeros((total_timesteps, len(STATIONS)), dtype=bool)

cleaning_log = []

for node_idx, sname in enumerate(STATIONS):
    era5_file = os.path.join(root_dir, "pipeline", "dataset", "processed", f"era5_{sname}.parquet")
    cwc_file = os.path.join(root_dir, "pipeline", "dataset", "processed", f"cwc_{sname}.parquet")
    
    # 1. Load ERA5
    df_era5 = pd.read_parquet(era5_file)
    if "timestamp" in df_era5.columns:
        df_era5["dt"] = pd.to_datetime(df_era5["timestamp"]).dt.tz_localize(None)
        df_era5 = df_era5.set_index("dt")
    num_cols = ["temperature_c", "humidity_pct", "wind_speed_ms", "pressure_pa", "evaporation_mm", "soil_moisture"]
    df_era5_numeric = df_era5[[c for c in num_cols if c in df_era5.columns]]
    df_era5_aligned = df_era5_numeric.reindex(common_timeline).interpolate(method="time").ffill().bfill()
    
    # 2. Load CWC
    df_cwc = pd.read_parquet(cwc_file)
    if not isinstance(df_cwc.index, pd.DatetimeIndex):
        df_cwc.index = pd.to_datetime(df_cwc.index)
        
    df_cwc_resampled = df_cwc.resample("1H").mean()
    df_cwc_aligned = df_cwc_resampled.reindex(common_timeline)
    
    # Cleaning & Short-gap Linear Interpolation (max 6 hours)
    valid_before = df_cwc_aligned["level_m"].notnull().sum()
    df_cwc_aligned["level_m_interp"] = df_cwc_aligned["level_m"].interpolate(method="time", limit=6)
    valid_after = df_cwc_aligned["level_m_interp"].notnull().sum()
    
    cleaning_log.append({
        "station": sname,
        "valid_before_interp": int(valid_before),
        "valid_after_interp": int(valid_after),
        "interpolated_added": int(valid_after - valid_before)
    })
    
    # Fill feature tensor
    X_raw[:, node_idx, 0] = df_era5_aligned["temperature_c"].values
    X_raw[:, node_idx, 1] = df_era5_aligned["humidity_pct"].values
    X_raw[:, node_idx, 2] = df_era5_aligned["wind_speed_ms"].values
    X_raw[:, node_idx, 3] = df_era5_aligned["pressure_pa"].values
    X_raw[:, node_idx, 4] = df_era5_aligned["evaporation_mm"].values
    X_raw[:, node_idx, 5] = df_era5_aligned["soil_moisture"].values
    X_raw[:, node_idx, 6] = ELEVATIONS[sname]
    
    # Fill target tensor
    Y_raw[:, node_idx] = df_cwc_aligned["level_m_interp"].fillna(0.0).values
    Y_mask[:, node_idx] = df_cwc_aligned["level_m_interp"].notnull().values

print(f"Data Cleaning & Feature Assembly Complete across {len(STATIONS)} stations.")

# Step 10: Train / Validation / Test Chronological Split (70% Train, 15% Val, 15% Test)
train_split_idx = int(0.70 * total_timesteps)
val_split_idx = int(0.85 * total_timesteps)

# Step 6: Normalize numerical features using StandardScaler fitted ONLY on Train set
scaler = StandardScaler()
X_train_flat = X_raw[:train_split_idx].reshape(-1, len(FEATURE_COLS))
scaler.fit(X_train_flat)

X_scaled = np.zeros_like(X_raw)
for t in range(total_timesteps):
    X_scaled[t] = scaler.transform(X_raw[t])

# Save Scaler
scaler_path = os.path.join(out_dir, "scaler.pkl")
with open(scaler_path, "wb") as f:
    pickle.dump(scaler, f)

print(f"StandardScaler fitted on train set ({train_split_idx} steps) and saved to {scaler_path}.")

# Step 8: Sliding Window Sequence Generation
# History Window = 24 hours (24 steps), Target Horizons = +6h, +12h, +24h
HIST_LEN = 24
PRED_HORIZONS = [6, 12, 24]  # Multi-horizon forecast
MAX_HORIZON = max(PRED_HORIZONS)

train_graphs = []
val_graphs = []
test_graphs = []

for t in range(HIST_LEN, total_timesteps - MAX_HORIZON):
    # History window node feature tensor: Shape (8, 24, 7)
    x_seq = torch.tensor(X_scaled[t - HIST_LEN:t].transpose(1, 0, 2), dtype=torch.float32)
    # Current step node feature snapshot: Shape (8, 7)
    x_curr = torch.tensor(X_scaled[t - 1], dtype=torch.float32)
    
    # Target tensor for multi-horizon (+6h, +12h, +24h): Shape (8, 3)
    y_horizons = []
    for h in PRED_HORIZONS:
        y_horizons.append(Y_raw[t + h - 1])
    y_target = torch.tensor(np.column_stack(y_horizons), dtype=torch.float32)
    
    # Target validity mask: Shape (8, 3)
    m_horizons = []
    for h in PRED_HORIZONS:
        m_horizons.append(Y_mask[t + h - 1])
    y_mask_tensor = torch.tensor(np.column_stack(m_horizons), dtype=torch.bool)
    
    ts_str = str(common_timeline[t])
    
    # PyTorch Geometric Data Dictionary / Object
    graph_dict = {
        "x": x_curr,                    # Current node features (8, 7)
        "x_seq": x_seq,                # History sequence features (8, 24, 7)
        "edge_index": edge_index,      # Directed reach edges (2, 7)
        "edge_attr": edge_attr,        # Edge physical attributes (7, 3)
        "y": y_target,                 # Multi-horizon water level targets (8, 3)
        "y_mask": y_mask_tensor,       # Target validity mask (8, 3)
        "timestamp": ts_str,
        "stations": STATIONS
    }
    
    if t < train_split_idx:
        train_graphs.append(graph_dict)
    elif t < val_split_idx:
        val_graphs.append(graph_dict)
    else:
        test_graphs.append(graph_dict)

print(f"Sliding Window Generation Complete:")
print(f"  Train Graph Snapshots : {len(train_graphs)}")
print(f"  Val Graph Snapshots   : {len(val_graphs)}")
print(f"  Test Graph Snapshots  : {len(test_graphs)}")
print(f"  Total Graph Snapshots : {len(train_graphs) + len(val_graphs) + len(test_graphs)}")

# Step 11 & 13: Save PyTorch Datasets & Metadata
torch.save(train_graphs, os.path.join(out_dir, "train.pt"))
torch.save(val_graphs, os.path.join(out_dir, "val.pt"))
torch.save(test_graphs, os.path.join(out_dir, "test.pt"))

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
    "target_units": "meters",
    "normalization": "StandardScaler (fitted on train split only)",
    "elevations_m": ELEVATIONS
}

preprocessing_config = {
    "project": "HydroGNN-Net",
    "model_architecture": "GRU + GATv2 + GraphSAGE Spatio-Temporal Flood Router",
    "sampling_frequency": "1-Hour Uniform Grid",
    "missing_value_strategy": "Time Interpolation (limit=6h) + Train Scaler Normalization",
    "split_ratios": {"train": 0.70, "val": 0.15, "test": 0.15},
    "history_window_hours": 24,
    "forecast_horizons_hours": [6, 12, 24],
    "torch_geometric_version": torch.__version__
}

with open(os.path.join(out_dir, "graph_metadata.json"), "w") as f:
    json.dump(graph_metadata, f, indent=2)

with open(os.path.join(out_dir, "feature_info.json"), "w") as f:
    json.dump(feature_info, f, indent=2)

with open(os.path.join(out_dir, "preprocessing_config.yaml"), "w") as f:
    yaml.dump(preprocessing_config, f, default_flow_style=False)

print("PyTorch Geometric Dataset Construction Pipeline Finished Successfully!")
print(f"Output files saved to: {out_dir}")
