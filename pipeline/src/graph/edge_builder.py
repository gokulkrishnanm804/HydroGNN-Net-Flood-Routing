"""
Graph edge builder for HydroGNN-Net.

Builds directed edges (upstream → downstream) from HydroRIVERS or geographic fallback.

Edge features:
    length_km      River segment length between stations
    elev_diff_m    Elevation difference (upstream − downstream)
    travel_time_h  length_km / default_velocity_kmh
    strahler_order Strahler stream order from HydroRIVERS or estimated
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import pandas as pd
import torch
from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger(__name__)


class EdgeBuilder:
    """
    Constructs the directed river network graph edges.

    Primary method   : HydroRIVERS river network (if shapefile available).
    Fallback method  : Geographic heuristic using elevation and basin area.
    """

    def __init__(self, config: dict) -> None:
        self.config       = config
        self.velocity_kmh = config["graph"]["default_velocity_kmh"]

    # ------------------------------------------------------------------ #
    # Fallback connectivity
    # ------------------------------------------------------------------ #

    def build_fallback_connectivity(
        self,
        nodes_df: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Build river connectivity from station metadata (no HydroRIVERS).

        Rules:
        1. Sort stations by basin_area_km2 ascending (smaller = more upstream).
        2. Connect pairs on the same river where the smaller-area station
           has no intermediate station between it and the larger-area one.
        3. Edge direction: smaller basin → larger basin (upstream → downstream).

        Returns
        -------
        (edges_df, edge_attrs_df)
        """
        logger.warning(
            "HydroRIVERS not available. Using geographic fallback for river connectivity.\n"
            "Connectivity is inferred from station elevation and basin area."
        )

        nodes = nodes_df.sort_values("basin_area_km2").reset_index(drop=True)
        edges, attrs = [], []

        # Pre-build a lookup: {river_name: sorted station rows}
        river_col = nodes["river"] if "river" in nodes.columns else pd.Series([""] * len(nodes), index=nodes.index)

        for i, row_u in nodes.iterrows():
            river_u = river_col.iloc[i]
            for j, row_d in nodes.iterrows():
                if i >= j:
                    continue  # only consider pairs where row_u has smaller basin (upstream)
                river_d = river_col.iloc[j]
                if river_u != river_d:
                    continue

                elev_u = float(row_u["elevation_m"]) if pd.notna(row_u["elevation_m"]) else float("nan")
                elev_d = float(row_d["elevation_m"]) if pd.notna(row_d["elevation_m"]) else float("nan")
                if pd.isna(elev_u) or pd.isna(elev_d) or elev_u <= elev_d:
                    continue   # upstream must be higher elevation

                # Reject if any intermediate station exists on the same river
                # with basin_area between the two stations
                area_u = float(row_u["basin_area_km2"])
                area_d = float(row_d["basin_area_km2"])
                interm_mask = (
                    (nodes.index != i) &
                    (nodes.index != j) &
                    (nodes["basin_area_km2"] > area_u) &
                    (nodes["basin_area_km2"] < area_d) &
                    (river_col == river_u)
                )
                if interm_mask.any():
                    continue

                dist      = self._haversine(row_u["lat"], row_u["lon"],
                                            row_d["lat"], row_d["lon"])
                tt_h      = dist / self.velocity_kmh
                elev_diff = max(0.0, elev_u - elev_d)
                area      = float(row_d["basin_area_km2"])
                strahler  = max(1, min(8, int(np.ceil(np.log2(max(area, 100) / 100.0)))))

                edges.append({"src_id": row_u["station_id"], "dst_id": row_d["station_id"]})
                attrs.append({
                    "src_id":         row_u["station_id"],
                    "dst_id":         row_d["station_id"],
                    "length_km":      round(dist, 2),
                    "elev_diff_m":    round(elev_diff, 1),
                    "travel_time_h":  round(tt_h, 3),
                    "strahler_order": strahler,
                })

        edges_df = pd.DataFrame(edges) if edges else pd.DataFrame(columns=["src_id", "dst_id"])
        attrs_df = pd.DataFrame(attrs) if attrs else pd.DataFrame()
        logger.info(f"Fallback: {len(edges_df)} edges built from {len(nodes_df)} stations")
        return edges_df, attrs_df

    # ------------------------------------------------------------------ #
    # Adjacency matrix
    # ------------------------------------------------------------------ #

    def compute_adjacency_matrix(
        self,
        edges_df: pd.DataFrame,
        node_ids: list,
    ) -> np.ndarray:
        """Return binary adjacency matrix [N, N]."""
        n       = len(node_ids)
        idx_map = {sid: i for i, sid in enumerate(node_ids)}
        adj     = np.zeros((n, n), dtype=float)
        for _, row in edges_df.iterrows():
            i = idx_map.get(row["src_id"])
            j = idx_map.get(row["dst_id"])
            if i is not None and j is not None:
                adj[i, j] = 1.0
        return adj

    # ------------------------------------------------------------------ #
    # PyG format
    # ------------------------------------------------------------------ #

    def to_pyg_format(
        self,
        edges_df: pd.DataFrame,
        edge_attrs_df: pd.DataFrame,
        node_ids: list,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Convert edges to PyG COO format.

        Returns
        -------
        (edge_index [2, E], edge_attr [E, 4])
        """
        idx_map    = {sid: i for i, sid in enumerate(node_ids)}
        feat_cols  = ["length_km", "elev_diff_m", "travel_time_h", "strahler_order"]
        src_list, dst_list, attr_list = [], [], []

        for _, row in edges_df.iterrows():
            i = idx_map.get(row["src_id"])
            j = idx_map.get(row["dst_id"])
            if i is None or j is None:
                continue

            # Find matching edge attributes
            if not edge_attrs_df.empty:
                mask = (
                    (edge_attrs_df["src_id"] == row["src_id"]) &
                    (edge_attrs_df["dst_id"] == row["dst_id"])
                )
                matched = edge_attrs_df[mask]
                if len(matched) > 0:
                    attr_vals = [float(matched.iloc[0].get(c, 0)) for c in feat_cols]
                else:
                    attr_vals = [0.0] * len(feat_cols)
            else:
                attr_vals = [0.0] * len(feat_cols)

            src_list.append(i)
            dst_list.append(j)
            attr_list.append(attr_vals)

        if not src_list:
            # Self-loop fallback (ensures graph connectivity for any single node)
            n = len(node_ids)
            edge_index = torch.zeros((2, n), dtype=torch.long)
            for i in range(n):
                edge_index[0, i] = i
                edge_index[1, i] = i
            edge_attr = torch.zeros((n, len(feat_cols)), dtype=torch.float)
            logger.warning("No directed edges found — adding self-loops as fallback")
            return edge_index, edge_attr

        edge_index = torch.tensor([src_list, dst_list], dtype=torch.long)
        edge_attr  = torch.tensor(attr_list, dtype=torch.float)
        return edge_index, edge_attr

    # ------------------------------------------------------------------ #
    # Save
    # ------------------------------------------------------------------ #

    def save(
        self,
        edges_df: pd.DataFrame,
        edge_attrs_df: pd.DataFrame,
        adj_matrix: np.ndarray,
        output_dir: Path,
    ) -> None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        edges_df.to_csv(output_dir / "edges.csv", index=False)
        if not edge_attrs_df.empty:
            edge_attrs_df.to_csv(output_dir / "edge_attributes.csv", index=False)
        np.save(output_dir / "adjacency_matrix.npy", adj_matrix)
        logger.info(
            f"Graph saved: {len(edges_df)} edges, "
            f"adjacency {adj_matrix.shape} → {output_dir}"
        )

    # ------------------------------------------------------------------ #
    # Haversine helper
    # ------------------------------------------------------------------ #

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Haversine great-circle distance in km."""
        R    = 6371.0
        phi1 = np.radians(lat1)
        phi2 = np.radians(lat2)
        dphi = np.radians(lat2 - lat1)
        dlam = np.radians(lon2 - lon1)
        a    = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2) ** 2
        return R * 2 * np.arcsin(np.sqrt(a))
