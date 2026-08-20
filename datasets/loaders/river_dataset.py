import os
import json
import torch
import numpy as np
import pandas as pd
from torch.utils.data import Dataset

class RiverBasinDataset(Dataset):
    def __init__(self, data_path, graph_path, lookback=24, horizon=96, step=4, mode="train"):
        """
        Args:
            data_path: Path to flood_data.csv
            graph_path: Path to graph_topology.json
            lookback: Number of historical steps to look back (e.g. 24 steps = 6 hours)
            horizon: Number of future steps to forecast (e.g. 96 steps = 24 hours)
            step: Sliding window step
            mode: "train", "val", or "test"
        """
        self.lookback = lookback
        self.horizon = horizon
        
        # Load static graph info
        with open(graph_path, "r") as f:
            self.graph_info = json.load(f)
            
        self.stations = self.graph_info["stations"]
        self.station_ids = [s["id"] for s in self.stations]
        self.node_to_idx = self.graph_info["node_to_idx"]
        self.num_nodes = len(self.stations)
        
        # Static features per node: elevation, is_reservoir
        self.static_features = np.zeros((self.num_nodes, 2))
        max_elev = max([s["elevation"] for s in self.stations])
        for idx, s in enumerate(self.stations):
            self.static_features[idx, 0] = s["elevation"] / max_elev
            self.static_features[idx, 1] = 1.0 if s["type"] == "reservoir" else 0.0
            
        # Load timeseries data
        df = pd.read_csv(data_path)
        df["ts"] = pd.to_datetime(df["ts"])
        
        # Group by station
        station_dfs = {sid: df[df["station_id"] == sid].sort_values("ts").copy() for sid in self.station_ids}
        self.timestamps = station_dfs[self.station_ids[0]]["ts"].values
        self.total_steps = len(self.timestamps)
        
        # Node features to extract (excluding target water_level/discharge)
        # Features: rain_observed, soil_moisture, temperature, humidity
        self.feature_cols = ["rain_observed", "soil_moisture", "temperature", "humidity"]
        self.forecast_cols = ["rain_forecast_6h", "rain_forecast_24h", "rain_forecast_72h"]
        
        # Normalize features
        self.raw_data = {}
        self.means = {}
        self.stds = {}
        
        # Calculate means/stds across train split (first 70% of dataset)
        train_cutoff = int(self.total_steps * 0.7)
        
        for col in self.feature_cols + self.forecast_cols + ["water_level", "discharge"]:
            vals = []
            for sid in self.station_ids:
                vals.extend(station_dfs[sid][col].values[:train_cutoff])
            self.means[col] = np.mean(vals)
            self.stds[col] = np.std(vals) if np.std(vals) > 0 else 1.0
            
        # Create standard arrays: [total_steps, num_nodes, num_features]
        # Features will be:
        # 0: rain_observed (normalized)
        # 1: soil_moisture (raw, 0-1)
        # 2: temp (normalized)
        # 3: humidity (normalized)
        # 4: static_elevation
        # 5: static_is_reservoir
        # 6: water_level (last step observed, normalized)
        # 7: discharge (last step observed, normalized)
        self.node_features = np.zeros((self.total_steps, self.num_nodes, 8))
        self.targets_level = np.zeros((self.total_steps, self.num_nodes))
        self.targets_discharge = np.zeros((self.total_steps, self.num_nodes))
        
        # Forecast weather rain arrays: [total_steps, num_nodes, 3] (6h, 24h, 72h forecast)
        self.forecast_weather = np.zeros((self.total_steps, self.num_nodes, 3))
        
        for idx, sid in enumerate(self.station_ids):
            sdf = station_dfs[sid]
            # Normalize
            rain_norm = (sdf["rain_observed"].values - self.means["rain_observed"]) / self.stds["rain_observed"]
            temp_norm = (sdf["temperature"].values - self.means["temperature"]) / self.stds["temperature"]
            hum_norm = (sdf["humidity"].values - self.means["humidity"]) / self.stds["humidity"]
            wl_norm = (sdf["water_level"].values - self.means["water_level"]) / self.stds["water_level"]
            q_norm = (sdf["discharge"].values - self.means["discharge"]) / self.stds["discharge"]
            
            # Forecasts
            rf_6 = (sdf["rain_forecast_6h"].values - self.means["rain_forecast_6h"]) / self.stds["rain_forecast_6h"]
            rf_24 = (sdf["rain_forecast_24h"].values - self.means["rain_forecast_24h"]) / self.stds["rain_forecast_24h"]
            rf_72 = (sdf["rain_forecast_72h"].values - self.means["rain_forecast_72h"]) / self.stds["rain_forecast_72h"]
            
            self.node_features[:, idx, 0] = rain_norm
            self.node_features[:, idx, 1] = sdf["soil_moisture"].values
            self.node_features[:, idx, 2] = temp_norm
            self.node_features[:, idx, 3] = hum_norm
            self.node_features[:, idx, 4] = self.static_features[idx, 0]
            self.node_features[:, idx, 5] = self.static_features[idx, 1]
            self.node_features[:, idx, 6] = wl_norm
            self.node_features[:, idx, 7] = q_norm
            
            self.targets_level[:, idx] = sdf["water_level"].values
            self.targets_discharge[:, idx] = sdf["discharge"].values
            
            self.forecast_weather[:, idx, 0] = rf_6
            self.forecast_weather[:, idx, 1] = rf_24
            self.forecast_weather[:, idx, 2] = rf_72
            
        # Delineate split indices
        # Train: 0% to 70%, Val: 70% to 85%, Test: 85% to 100%
        val_cutoff = int(self.total_steps * 0.85)
        
        if mode == "train":
            self.start_idx = 0
            self.end_idx = train_cutoff - self.lookback - self.horizon
        elif mode == "val":
            self.start_idx = train_cutoff
            self.end_idx = val_cutoff - self.lookback - self.horizon
        else: # test
            self.start_idx = val_cutoff
            self.end_idx = self.total_steps - self.lookback - self.horizon
            
        self.indices = list(range(self.start_idx, self.end_idx, step))
        
        # Edge Index (static for message passing)
        self.edge_index = torch.tensor(self.graph_info["edge_index"], dtype=torch.long)
        self.edge_travel_times = torch.tensor(self.graph_info["edge_travel_times"], dtype=torch.float32)
        
    def __len__(self):
        return len(self.indices)
        
    def __getitem__(self, idx):
        start = self.indices[idx]
        hist_end = start + self.lookback
        fut_end = hist_end + self.horizon
        
        # Historical node features: [L, N, d]
        hist_x = self.node_features[start:hist_end]
        
        # Future forecast weather features: [H, N, 3]
        fut_w = self.forecast_weather[hist_end:fut_end]
        
        # Future targets: [H, N]
        fut_y = self.targets_level[hist_end:fut_end]
        fut_q = self.targets_discharge[hist_end:fut_end]
        
        return {
            "hist_x": torch.tensor(hist_x, dtype=torch.float32),
            "fut_w": torch.tensor(fut_w, dtype=torch.float32),
            "fut_y": torch.tensor(fut_y, dtype=torch.float32),
            "fut_q": torch.tensor(fut_q, dtype=torch.float32),
            "edge_index": self.edge_index,
            "edge_travel_times": self.edge_travel_times
        }
