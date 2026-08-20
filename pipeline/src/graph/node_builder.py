"""
Graph node builder for HydroGNN-Net.
Creates nodes.csv from station metadata and terrain attributes.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


class NodeBuilder:
    """Builds the GNN node attribute table from station configuration and terrain."""

    def __init__(self, config: dict) -> None:
        self.config = config

    def build_nodes_csv(
        self,
        station_configs: list,
        terrain_df: pd.DataFrame,
        reservoir_configs: Optional[list] = None,
    ) -> pd.DataFrame:
        """
        Build nodes DataFrame from station metadata and terrain.

        Parameters
        ----------
        station_configs  : List of station dicts from config.yaml.
        terrain_df       : DataFrame with [station_id, elevation_m, slope_deg].
        reservoir_configs: Optional list of reservoir dicts.

        Returns
        -------
        pd.DataFrame columns:
            node_id, station_id, name, lat, lon, elevation_m, slope_deg,
            danger_level_m, warning_level_m, basin_area_km2, is_reservoir,
            district, river
        """
        # Index terrain by station_id for fast lookup
        terrain_map = {}
        if terrain_df is not None and not terrain_df.empty:
            for _, row in terrain_df.iterrows():
                terrain_map[row["station_id"]] = row

        rows = []
        for i, st in enumerate(station_configs):
            sid     = st["id"]
            t_row   = terrain_map.get(sid)  # Series or None
            has_terrain = t_row is not None
            elev    = float(t_row["elevation_m"]) if has_terrain and pd.notna(t_row.get("elevation_m")) else np.nan
            slope   = float(t_row["slope_deg"])   if has_terrain and pd.notna(t_row.get("slope_deg"))   else np.nan

            rows.append({
                "node_id":         i,
                "station_id":      sid,
                "name":            st["name"],
                "lat":             st["lat"],
                "lon":             st["lon"],
                "elevation_m":     elev,
                "slope_deg":       slope,
                "danger_level_m":  st["danger_level_m"],
                "warning_level_m": st.get("warning_level_m", st["danger_level_m"] * 0.8),
                "basin_area_km2":  st.get("basin_area_km2", 0),
                "is_reservoir":    int(st.get("is_reservoir", False)),
                "district":        st.get("district", ""),
                "river":           st.get("river", "Cauvery"),
            })

        nodes_df = pd.DataFrame(rows)
        logger.info(f"Built {len(nodes_df)} nodes")
        return nodes_df

    def save(self, nodes_df: pd.DataFrame, output_path: Path) -> None:
        """Save nodes DataFrame as CSV."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        nodes_df.to_csv(output_path, index=False)
        logger.info(f"Nodes saved: {output_path}")

    def load(self, path: Path) -> pd.DataFrame:
        """Load nodes from CSV."""
        return pd.read_csv(path)
