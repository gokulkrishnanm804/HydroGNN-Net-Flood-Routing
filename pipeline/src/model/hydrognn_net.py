"""
HydroGNN-Net: Physics-Informed Spatio-Temporal Graph Neural Network
for Real-Time Multi-Scale Flood Forecasting

Architecture
------------

    Input: x [N, T=48, F=13]
           edge_index [2, E],  edge_attr [E, 4]
                │
                ▼
    ┌─────────────────────────────────────────┐
    │  TemporalEncoder                        │
    │  GRU(input=13, hidden=128, layers=2)    │
    │  → h_t [N, 128]                         │
    └─────────────────────────────────────────┘
                │
                ▼
    ┌─────────────────────────────────────────┐
    │  GATv2Encoder  (2 layers)               │
    │  GATv2Conv(128→64, heads=4, edge_dim=4) │
    │  → [N, 256]  (64 × 4 heads, concat)     │
    │  LayerNorm + ELU + Dropout              │
    └─────────────────────────────────────────┘
                │
                ▼
    ┌─────────────────────────────────────────┐
    │  SAGERefinement                         │
    │  SAGEConv(256 → 128)  + ELU            │
    │  → [N, 128]                             │
    └─────────────────────────────────────────┘
                │
         ┌──────┴──────┐
         ▼             ▼
    MultiHorizon   Uncertainty
       Head           Head
    [N, H=6]       [N, H=6]
    (meters)      (log-var)

References
----------
Brody, S., Alon, U. & Yahav, E. (2022). How Attentive are Graph Attention Networks?
    ICLR 2022. https://arxiv.org/abs/2105.14491

Hamilton, W., Ying, R. & Leskovec, J. (2017). Inductive Representation Learning on
    Large Graphs. NeurIPS 2017. https://arxiv.org/abs/1706.02216

Cho, K. et al. (2014). Learning Phrase Representations using RNN Encoder-Decoder.
    EMNLP 2014. https://arxiv.org/abs/1406.1078
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import torch
import torch.nn as nn
from torch import Tensor

try:
    from torch_geometric.nn import GATv2Conv, SAGEConv
except ImportError:
    raise ImportError(
        "torch_geometric is required.\n"
        "Install: pip install torch_geometric\n"
        "See: https://pytorch-geometric.readthedocs.io"
    )

from .heads import MultiHorizonHead, UncertaintyHead


# ─────────────────────────────────────────────────────────────────────────────
# Sub-modules
# ─────────────────────────────────────────────────────────────────────────────

class TemporalEncoder(nn.Module):
    """
    Bidirectional-capable GRU that encodes the lookback window [N, T, F] → [N, hidden].

    Only the final hidden state is used as the temporal summary vector.
    """

    def __init__(
        self,
        input_size: int,
        hidden_size: int,
        num_layers: int = 2,
        dropout: float = 0.2,
    ) -> None:
        super().__init__()
        self.rnn = nn.GRU(
            input_size  = input_size,
            hidden_size = hidden_size,
            num_layers  = num_layers,
            batch_first = True,         # expects [batch, seq, features]
            dropout     = dropout if num_layers > 1 else 0.0,
        )
        self.norm = nn.LayerNorm(hidden_size)

    def forward(self, x: Tensor) -> Tensor:
        """
        Parameters
        ----------
        x : [N, T, F]  per-node lookback sequences

        Returns
        -------
        Tensor [N, hidden_size]  final hidden state
        """
        # x shape: [N, T, F]
        _, h_n = self.rnn(x)   # h_n: [num_layers, N, hidden]
        h_last = h_n[-1]        # [N, hidden]  — last layer
        return self.norm(h_last)


class GATv2Encoder(nn.Module):
    """
    Stack of GATv2Conv layers for spatial graph attention.

    Uses edge features (length_km, elev_diff_m, travel_time_h, strahler_order)
    to guide attention weights.
    """

    def __init__(
        self,
        in_channels: int,
        out_per_head: int,
        heads: int,
        num_layers: int,
        edge_dim: int,
        dropout: float = 0.2,
    ) -> None:
        super().__init__()
        self.convs  = nn.ModuleList()
        self.norms  = nn.ModuleList()
        self.dropout = dropout

        cur_in = in_channels
        for _ in range(num_layers):
            self.convs.append(
                GATv2Conv(
                    in_channels  = cur_in,
                    out_channels = out_per_head,
                    heads        = heads,
                    edge_dim     = edge_dim,
                    dropout      = dropout,
                    concat       = True,
                )
            )
            self.norms.append(nn.LayerNorm(out_per_head * heads))
            cur_in = out_per_head * heads   # concat: input doubles each layer

        self.act     = nn.ELU()
        self.drop_fn = nn.Dropout(dropout)
        self.out_channels = cur_in

        # Residual projections: align in_channels → out_channels per layer
        in_sizes = [in_channels] + [out_per_head * heads] * (num_layers - 1)
        self.res_projs = nn.ModuleList()
        for in_s, out_s in zip(in_sizes, [out_per_head * heads] * num_layers):
            if in_s == out_s:
                self.res_projs.append(nn.Identity())
            else:
                self.res_projs.append(nn.Linear(in_s, out_s, bias=False))

    def forward(
        self,
        x: Tensor,
        edge_index: Tensor,
        edge_attr: Tensor,
        return_attention: bool = False,
    ) -> Tuple[Tensor, Optional[list]]:
        """
        Parameters
        ----------
        x            : [N, in_channels]
        edge_index   : [2, E]
        edge_attr    : [E, edge_dim]
        return_attention : If True, returns list of attention weight tensors.

        Returns
        -------
        (h, attn_weights)  where h: [N, out_channels]
        """
        attn_list = []
        h = x

        for i, (conv, norm, res_proj) in enumerate(zip(self.convs, self.norms, self.res_projs)):
            h_res = res_proj(h)   # project residual to match output dim
            if return_attention:
                h_new, attn = conv(h, edge_index, edge_attr, return_attention_weights=True)
                attn_list.append(attn)
            else:
                h_new = conv(h, edge_index, edge_attr)

            h_new = norm(h_new + h_res)  # residual addition before norm
            h_new = self.act(h_new)
            if i < len(self.convs) - 1:
                h_new = self.drop_fn(h_new)
            h = h_new

        return h, (attn_list if return_attention else None)


class SAGERefinement(nn.Module):
    """
    GraphSAGE refinement layer for aggregating neighborhood information.

    Applied after GATv2 to smooth spatial representations using mean aggregation.
    Reference: Hamilton et al. (2017).
    """

    def __init__(self, in_channels: int, out_channels: int) -> None:
        super().__init__()
        self.conv = SAGEConv(in_channels, out_channels, aggr="mean")
        self.norm = nn.LayerNorm(out_channels)
        self.act  = nn.ELU()

    def forward(self, x: Tensor, edge_index: Tensor) -> Tensor:
        h = self.conv(x, edge_index)
        return self.act(self.norm(h))


# ─────────────────────────────────────────────────────────────────────────────
# HydroGNN-Net
# ─────────────────────────────────────────────────────────────────────────────

class HydroGNNNet(nn.Module):
    """
    Physics-Informed Spatio-Temporal Graph Neural Network for Flood Forecasting.

    Full pipeline:
        [N, T, F] → GRU → GATv2 → SAGE → MultiHorizonHead + UncertaintyHead

    Parameters
    ----------
    node_features  : Number of input features per node per timestep (F=13).
    hidden_dim     : GRU hidden dimension (default 128).
    gru_layers     : Number of GRU layers (default 2).
    gat_heads      : Number of GATv2 attention heads (default 4).
    gat_layers     : Number of GATv2 layers (default 2).
    sage_hidden    : SAGEConv output dimension (default 128).
    edge_dim       : Number of edge feature dimensions (default 4).
    dropout        : Dropout probability (default 0.2).
    horizons       : Forecast horizons in hours (default [1,3,6,12,18,24]).
    """

    def __init__(
        self,
        node_features: int = 13,
        hidden_dim:    int = 128,
        gru_layers:    int = 2,
        gat_heads:     int = 4,
        gat_layers:    int = 2,
        sage_hidden:   int = 128,
        edge_dim:      int = 4,
        dropout:       float = 0.2,
        horizons:      List[int] = None,
    ) -> None:
        super().__init__()
        if horizons is None:
            horizons = [1, 3, 6, 12, 18, 24]
        self.horizons = horizons

        # 1. Temporal encoder: GRU
        self.temporal_encoder = TemporalEncoder(
            input_size  = node_features,
            hidden_size = hidden_dim,
            num_layers  = gru_layers,
            dropout     = dropout,
        )

        # 2. Spatial encoder: GATv2
        gat_per_head = hidden_dim // gat_heads  # e.g. 128//4 = 32
        self.gat_encoder = GATv2Encoder(
            in_channels  = hidden_dim,
            out_per_head = gat_per_head,
            heads        = gat_heads,
            num_layers   = gat_layers,
            edge_dim     = edge_dim,
            dropout      = dropout,
        )
        gat_out_dim = gat_per_head * gat_heads  # e.g. 32*4 = 128

        # 3. Refinement: GraphSAGE
        self.sage_refinement = SAGERefinement(gat_out_dim, sage_hidden)

        # 4. Prediction heads
        self.forecast_head     = MultiHorizonHead(sage_hidden, horizons, dropout=dropout)
        self.uncertainty_head  = UncertaintyHead(sage_hidden, horizons)

    # ------------------------------------------------------------------ #
    # Forward
    # ------------------------------------------------------------------ #

    def forward(
        self,
        x: Tensor,
        edge_index: Tensor,
        edge_attr: Tensor,
        return_attention: bool = False,
    ) -> Tuple[Tensor, Tensor]:
        """
        Parameters
        ----------
        x            : [N, T, F]  node feature sequences (normalized)
        edge_index   : [2, E]     COO edge connectivity
        edge_attr    : [E, 4]     edge features
        return_attention: Not yet used (reserved for GNN-XAI).

        Returns
        -------
        (pred, log_var)
            pred    : [N, H]  predicted water level at each horizon
            log_var : [N, H]  log-variance for uncertainty quantification
        """
        # 1. Temporal encoding: Passes normalized lookback feature sequence [N, T=48, F=13] through GRU to extract temporal hidden state [N, hidden=128].
        h_t = self.temporal_encoder(x)

        # 2. Spatial encoding: Passes temporal representation h_t and graph connectivity [2, E] with edge features [E, 4] through GATv2 multi-head attention.
        h_s, _ = self.gat_encoder(h_t, edge_index, edge_attr)

        # 3. Spatial SAGE refinement: Smooths node feature representations via GraphSAGE mean neighborhood aggregation [N, 128].
        h_r = self.sage_refinement(h_s, edge_index)

        # 4. Multi-horizon prediction heads: Computes water level predictions [N, H] and log-variance uncertainty bounds [N, H].
        pred    = self.forecast_head(h_r)      # [N, H]  Water level forecasts (meters)
        log_var = self.uncertainty_head(h_r)   # [N, H]  Aleatoric uncertainty (log-variance)

        return pred, log_var

    # ------------------------------------------------------------------ #
    # Inference utilities
    # ------------------------------------------------------------------ #

    @torch.no_grad()
    def predict_with_uncertainty(
        self,
        x: Tensor,
        edge_index: Tensor,
        edge_attr: Tensor,
        n_mc_samples: int = 20,
    ) -> Tuple[Tensor, Tensor, Tensor]:
        """
        Monte Carlo Dropout uncertainty estimation.

        Runs *n_mc_samples* forward passes with dropout active, returning:
        - mean prediction across samples
        - epistemic std  (std of MC sample means)
        - aleatoric std  (mean of exp(0.5 * log_var) across samples)

        Parameters
        ----------
        x, edge_index, edge_attr : Same as forward().
        n_mc_samples : Number of stochastic forward passes.

        Returns
        -------
        (mean_pred, epistemic_std, aleatoric_std)  each [N, H]
        """
        self.train()  # Enable dropout
        preds, alea_stds = [], []

        for _ in range(n_mc_samples):
            pred, log_var = self(x, edge_index, edge_attr)
            preds.append(pred.unsqueeze(0))
            alea_stds.append(torch.exp(0.5 * log_var).unsqueeze(0))

        self.eval()  # Restore eval mode

        preds_t     = torch.cat(preds, dim=0)         # [S, N, H]
        alea_stds_t = torch.cat(alea_stds, dim=0)     # [S, N, H]

        mean_pred      = preds_t.mean(dim=0)           # [N, H]
        epistemic_std  = preds_t.std(dim=0)            # [N, H]
        aleatoric_std  = alea_stds_t.mean(dim=0)       # [N, H]

        return mean_pred, epistemic_std, aleatoric_std

    @torch.no_grad()
    def get_attention_weights(
        self,
        x: Tensor,
        edge_index: Tensor,
        edge_attr: Tensor,
    ) -> list:
        """Return GATv2 attention weights for XAI/visualization."""
        self.eval()
        h_t = self.temporal_encoder(x)
        _, attn_list = self.gat_encoder(h_t, edge_index, edge_attr, return_attention=True)
        return attn_list or []

    def count_parameters(self) -> int:
        """Return the number of trainable parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    # ------------------------------------------------------------------ #
    # Factory
    # ------------------------------------------------------------------ #

    @classmethod
    def from_config(cls, model_cfg: dict) -> "HydroGNNNet":
        """
        Construct HydroGNNNet from a config.yaml model section.

        Parameters
        ----------
        model_cfg : dict from config.yaml['model']

        Returns
        -------
        HydroGNNNet instance
        """
        return cls(
            node_features = int(model_cfg.get("node_features", 13)),
            hidden_dim    = int(model_cfg.get("hidden_dim",    128)),
            gru_layers    = int(model_cfg.get("gru_layers",    2)),
            gat_heads     = int(model_cfg.get("gat_heads",     4)),
            gat_layers    = int(model_cfg.get("gat_layers",    2)),
            sage_hidden   = int(model_cfg.get("sage_hidden",   128)),
            edge_dim      = int(model_cfg.get("edge_dim",      4)),
            dropout       = float(model_cfg.get("dropout",     0.2)),
            horizons      = list(model_cfg.get("horizons",     [1, 3, 6, 12, 18, 24])),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Physics-informed loss
# ─────────────────────────────────────────────────────────────────────────────

class HydroGNNLoss(nn.Module):
    """
    Composite loss function for HydroGNN-Net training.

    L = w_mse   × MSE(pred, target)
      + w_nse   × (1 − NSE(pred, target))
      + w_phys  × continuity_violation
      [+ NLL term if log_var provided]

    Continuity violation:
        Penalises unphysical jumps > 5 m between consecutive horizon predictions.
        max(0, |pred[:, h+1] − pred[:, h]| − 5.0) for each h.

    Parameters
    ----------
    mse_weight    : Weight for MSE term (default 1.0).
    nse_weight    : Weight for NSE term (default 0.3).
    physics_weight: Weight for continuity violation term (default 0.1).
    """

    def __init__(
        self,
        mse_weight:     float = 1.0,
        nse_weight:     float = 0.3,
        physics_weight: float = 0.1,
    ) -> None:
        super().__init__()
        self.w_mse   = mse_weight
        self.w_nse   = nse_weight
        self.w_phys  = physics_weight

    def forward(
        self,
        pred:    Tensor,                   # [N, H]
        target:  Tensor,                   # [N, H]
        log_var: Optional[Tensor] = None,  # [N, H]
        mask:    Optional[Tensor] = None,  # [N] bool
    ) -> Tensor:
        """
        Compute total loss.

        Parameters
        ----------
        pred    : Predicted water levels [N, H].
        target  : True water levels [N, H].
        log_var : Log-variance for NLL term [N, H] (optional).
        mask    : Boolean mask — True where target is valid [N] (optional).
        """
        # Determine valid target mask
        valid = torch.isfinite(target)
        if mask is not None:
            valid = valid & mask

        if not valid.any():
            return pred.sum() * 0.0

        p = pred[valid]
        t = target[valid]
        lv_val = log_var[valid] if log_var is not None else None

        # 1. MSE loss
        loss_mse = nn.functional.mse_loss(p, t)

        # 2. NSE-based loss: minimize (1 - NSE)
        t_mean   = t.mean()
        ss_tot   = ((t - t_mean) ** 2).sum().clamp(min=1e-6)
        ss_res   = ((t - p) ** 2).sum()
        nse      = 1.0 - ss_res / ss_tot
        loss_nse = 1.0 - nse

        # 3. Physical continuity violation across consecutive horizon steps [N, H]
        if pred.ndim >= 2 and pred.shape[-1] > 1:
            diffs     = pred[:, 1:] - pred[:, :-1]             # [N, H-1]
            violation = nn.functional.relu(diffs.abs() - 5.0)  # >5m jump
            loss_phys = violation.mean()
        else:
            loss_phys = pred.new_zeros(1).squeeze()

        # 4. Negative Log-Likelihood (heteroscedastic)
        if lv_val is not None:
            residual  = p - t
            loss_nll  = 0.5 * (lv_val + (residual ** 2) * torch.exp(-lv_val))
            loss_nll  = loss_nll.mean()
        else:
            loss_nll = pred.new_zeros(1).squeeze()

        total = (
            self.w_mse  * loss_mse
            + self.w_nse  * loss_nse
            + self.w_phys * loss_phys
            + loss_nll
        )
        return total
