"""
HydroGNN-Net — Prediction heads for multi-horizon flood forecasting.

MultiHorizonHead : Predicts water level at each forecast horizon.
UncertaintyHead  : Predicts aleatoric uncertainty (log-variance) per horizon.
"""
from __future__ import annotations

from typing import List

import torch
import torch.nn as nn
from torch import Tensor


class MultiHorizonHead(nn.Module):
    """
    Multi-horizon water level prediction head.

    Architecture:
        Shared 2-layer MLP trunk → per-horizon linear output.

    Separate output layers per horizon ensure independence between short-range
    (dominated by current conditions) and long-range (dominated by routing)
    forecasts. The shared trunk extracts common representations efficiently.

    Parameters
    ----------
    in_channels : Feature dimension of input.
    horizons    : List of forecast horizon hours [1, 3, 6, 12, 18, 24].
    dropout     : Dropout probability in the trunk.

    Input  : Tensor [N, in_channels]
    Output : Tensor [N, H]  predicted water level at each horizon.
    """

    def __init__(
        self,
        in_channels: int,
        horizons: List[int] = None,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        if horizons is None:
            horizons = [1, 3, 6, 12, 18, 24]
        self.horizons = horizons
        H      = len(horizons)
        hidden = max(in_channels // 2, 32)

        # Shared trunk
        self.trunk = nn.Sequential(
            nn.Linear(in_channels, hidden),
            nn.ELU(),
            nn.Dropout(dropout),
        )
        # Per-horizon output layers
        self.heads = nn.ModuleList([
            nn.Linear(hidden, 1) for _ in range(H)
        ])

        # Weight initialisation
        for h in self.heads:
            nn.init.xavier_uniform_(h.weight)
            nn.init.zeros_(h.bias)

    def forward(self, x: Tensor) -> Tensor:
        """
        Parameters
        ----------
        x : [N, in_channels]

        Returns
        -------
        Tensor [N, H]
        """
        h     = self.trunk(x)                           # [N, hidden]
        preds = [head(h) for head in self.heads]        # H × [N, 1]
        return torch.cat(preds, dim=-1)                  # [N, H]


class UncertaintyHead(nn.Module):
    """
    Aleatoric uncertainty head for heteroscedastic regression.

    Outputs log-variance for each forecast horizon, allowing the model
    to express higher uncertainty at longer horizons naturally.

    σ (std) = exp(0.5 × log_var)
    95% CI  = pred ± 1.96 × σ

    Parameters
    ----------
    in_channels : Feature dimension of input.
    horizons    : List of forecast horizon hours.

    Input  : Tensor [N, in_channels]
    Output : Tensor [N, H]  log-variance values.
    """

    def __init__(
        self,
        in_channels: int,
        horizons: List[int] = None,
    ) -> None:
        super().__init__()
        if horizons is None:
            horizons = [1, 3, 6, 12, 18, 24]
        H      = len(horizons)
        hidden = max(in_channels // 4, 16)

        self.net = nn.Sequential(
            nn.Linear(in_channels, hidden),
            nn.ELU(),
            nn.Linear(hidden, H),
        )
        # Initialise to predict small uncertainty at training start (log_var ≈ −2 → std ≈ 0.37m)
        nn.init.constant_(self.net[-1].bias, -2.0)
        nn.init.xavier_uniform_(self.net[-1].weight, gain=0.1)

    def forward(self, x: Tensor) -> Tensor:
        """
        Parameters
        ----------
        x : [N, in_channels]

        Returns
        -------
        Tensor [N, H]  log-variance (clamped to [−6, 6] for stability).
        """
        log_var = self.net(x)
        return log_var.clamp(-6.0, 6.0)
