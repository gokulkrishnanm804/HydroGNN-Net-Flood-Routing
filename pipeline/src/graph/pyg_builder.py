"""
PyTorch Geometric Data object builder for HydroGNN-Net.

Creates one Data object per sliding window for training/evaluation.

Data shapes:
    x           [N, T_lookback, F]   Node feature sequences
    y           [N, H]               Target water levels at each horizon
    edge_index  [2, E]               COO graph connectivity
    edge_attr   [E, 4]               Edge features
    time_index  scalar               Unix timestamp of prediction point
    mask        [N]                  True where target is valid observed data
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd
import torch
from torch_geometric.data import Data

from src.utils.logger import get_logger

logger = get_logger(__name__)


class PyGGraphBuilder:
    """
    Constructs PyG Data objects via sliding window over the full time series.

    Parameters
    ----------
    config : Pipeline config dict (from config.yaml).
    """

    def __init__(self, config: dict) -> None:
        self.config         = config
        self.horizons_h     = config["temporal"]["forecast_horizons_hours"]
        self.horizon_steps  = [h * 2 for h in self.horizons_h]   # 30-min steps
        self.lookback       = config["temporal"]["lookback_steps"]  # 48

    # ------------------------------------------------------------------ #
    # Single Data object
    # ------------------------------------------------------------------ #

    def build_data_object(
        self,
        x:           np.ndarray,         # [N, lookback, F]
        y:           np.ndarray,         # [N, H]
        edge_index:  torch.Tensor,        # [2, E]
        edge_attr:   torch.Tensor,        # [E, 4]
        time_index:  int,                 # Unix timestamp
        mask:        Optional[np.ndarray] = None,  # [N]
    ) -> Data:
        """Build a single PyG Data object."""
        data = Data(
            x          = torch.tensor(x,          dtype=torch.float32),
            y          = torch.tensor(y,          dtype=torch.float32),
            edge_index = edge_index,
            edge_attr  = edge_attr,
            time_index = torch.tensor(time_index, dtype=torch.long),
        )
        if mask is not None:
            data.mask = torch.tensor(mask, dtype=torch.bool)
        return data

    # ------------------------------------------------------------------ #
    # Sliding windows
    # ------------------------------------------------------------------ #

    def build_sliding_windows(
        self,
        features:   np.ndarray,     # [T, N, F]
        targets:    np.ndarray,     # [T, N]
        masks:      np.ndarray,     # [T, N]
        timestamps: pd.DatetimeIndex,
        edge_index: torch.Tensor,
        edge_attr:  torch.Tensor,
        step:       int = 1,
    ) -> List[Data]:
        """
        Build all valid sliding-window Data objects.

        Window at time t:
            x : features[t − lookback : t]   → [N, lookback, F]
            y : targets[t + h_steps] for each horizon  → [N, H]

        A window is SKIPPED if:
        - Any forecast target index is out of bounds.
        - All nodes have invalid (NaN/False) targets at this time step.

        Parameters
        ----------
        features   : [T, N, F] normalised feature array.
        targets    : [T, N]    raw water level targets (metres).
        masks      : [T, N]    True where target is valid observed data.
        timestamps : pd.DatetimeIndex length T.
        edge_index, edge_attr : Static graph structure.
        step       : Window stride (1 = dense, 2 = every 2nd).

        Returns
        -------
        List of Data objects (chronologically ordered).
        """
        T, N, F     = features.shape
        max_horizon = max(self.horizon_steps)    # steps needed beyond t

        start   = self.lookback
        end     = T - max_horizon
        skipped = 0
        data_list: List[Data] = []

        if start >= end:
            logger.error(
                f"Dataset too short: T={T} steps, need at least {start + max_horizon}. "
                f"Ensure date range covers at least {(start + max_horizon) * 30 // 60}h of data."
            )
            return []

        for t in range(start, end, step):
            # Build x: lookback window, transposed to [N, lookback, F]
            x_window = features[t - self.lookback: t]   # [lookback, N, F]
            x_window = x_window.transpose(1, 0, 2)      # [N, lookback, F]

            # Build y: targets at each horizon
            y_window      = np.full((N, len(self.horizon_steps)), np.nan, dtype=np.float32)
            all_inbounds  = True
            for hi, hs in enumerate(self.horizon_steps):
                t_target = t + hs
                if t_target >= T:
                    all_inbounds = False
                    break
                y_window[:, hi] = targets[t_target]

            if not all_inbounds:
                skipped += 1
                continue

            # Skip windows with no valid target observations
            mask_t = masks[t]   # [N]
            if not np.any(mask_t):
                skipped += 1
                continue

            ts_unix = int(timestamps[t].timestamp())
            data    = self.build_data_object(
                x          = x_window.astype(np.float32),
                y          = y_window,
                edge_index = edge_index,
                edge_attr  = edge_attr,
                time_index = ts_unix,
                mask       = mask_t,
            )
            data_list.append(data)

        logger.info(
            f"Built {len(data_list):,} windows "
            f"(skipped {skipped:,}) "
            f"from T={T:,} timesteps "
            f"(lookback={self.lookback}, max_horizon={max_horizon})"
        )
        return data_list

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #

    def validate_graph(self, data: Data) -> bool:
        """Check a Data object for common structural issues."""
        ok = True
        if torch.any(torch.isnan(data.x)):
            logger.warning("NaN values detected in node features (data.x)")
            ok = False
        if data.edge_index.numel() > 0 and data.edge_index.max() >= data.x.shape[0]:
            logger.error(f"edge_index out of bounds: max={data.edge_index.max()}, N={data.x.shape[0]}")
            ok = False
        if data.y.shape[1] != len(self.horizons_h):
            logger.error(
                f"y horizon mismatch: got {data.y.shape[1]}, "
                f"expected {len(self.horizons_h)}"
            )
            ok = False
        return ok
