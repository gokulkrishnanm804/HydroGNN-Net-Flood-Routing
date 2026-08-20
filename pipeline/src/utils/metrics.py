"""
HydroGNN-Net Research Pipeline — Hydrological Performance Metrics

All metrics handle NaN values, degenerate inputs (zero variance, tiny arrays),
and return float('nan') rather than raising exceptions on edge cases.

References
----------
Nash, J.E. & Sutcliffe, J.V. (1970). River flow forecasting through conceptual
    models. Journal of Hydrology, 10(3), 282–290.
Kling, H. et al. (2012). Runoff conditions in the upper Danube basin under an
    ensemble of climate change scenarios. Journal of Hydrology, 424, 264–277.
"""
from __future__ import annotations

import numpy as np
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _clean(obs: np.ndarray, pred: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Remove NaN pairs and ensure at least 2 paired values."""
    obs  = np.asarray(obs,  dtype=float)
    pred = np.asarray(pred, dtype=float)
    mask = np.isfinite(obs) & np.isfinite(pred)
    return obs[mask], pred[mask]


# ─────────────────────────────────────────────────────────────────────────────
# Core metrics
# ─────────────────────────────────────────────────────────────────────────────

def nash_sutcliffe(obs: np.ndarray, pred: np.ndarray) -> float:
    """
    Nash–Sutcliffe Efficiency (NSE).

    NSE = 1 − Σ(obs−pred)² / Σ(obs−mean(obs))²

    Range: (−∞, 1].  NSE = 1 → perfect.  NSE < 0 → worse than mean.

    Parameters
    ----------
    obs, pred : array-like of float

    Returns
    -------
    float  NSE value, or nan if computation is impossible.
    """
    obs, pred = _clean(obs, pred)
    if len(obs) < 2:
        return float("nan")
    ss_res = np.sum((obs - pred) ** 2)
    ss_tot = np.sum((obs - obs.mean()) ** 2)
    if ss_tot < 1e-12:
        return float("nan")
    return float(1.0 - ss_res / ss_tot)


def kling_gupta(obs: np.ndarray, pred: np.ndarray) -> float:
    """
    Kling–Gupta Efficiency (KGE, 2012 version).

    KGE = 1 − √((r−1)² + (α−1)² + (β−1)²)

    where r = Pearson correlation, α = σ_pred/σ_obs, β = μ_pred/μ_obs.

    Range: (−∞, 1].  KGE = 1 → perfect.

    Parameters
    ----------
    obs, pred : array-like of float
    """
    obs, pred = _clean(obs, pred)
    if len(obs) < 2:
        return float("nan")
    mu_obs  = obs.mean()
    mu_pred = pred.mean()
    if mu_obs == 0 or obs.std() == 0 or pred.std() == 0:
        return float("nan")
    r = np.corrcoef(obs, pred)[0, 1]
    alpha = pred.std() / obs.std()
    beta  = mu_pred / mu_obs
    return float(1.0 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2))


def rmse(obs: np.ndarray, pred: np.ndarray) -> float:
    """Root Mean Square Error (m)."""
    obs, pred = _clean(obs, pred)
    if len(obs) == 0:
        return float("nan")
    return float(np.sqrt(np.mean((obs - pred) ** 2)))


def mae(obs: np.ndarray, pred: np.ndarray) -> float:
    """Mean Absolute Error (m)."""
    obs, pred = _clean(obs, pred)
    if len(obs) == 0:
        return float("nan")
    return float(np.mean(np.abs(obs - pred)))


def pbias(obs: np.ndarray, pred: np.ndarray) -> float:
    """
    Percent Bias (PBIAS, %).

    PBIAS = 100 × Σ(obs−pred) / Σ(obs)

    Positive → model under-predicts. Negative → model over-predicts.
    """
    obs, pred = _clean(obs, pred)
    if len(obs) == 0 or abs(obs.sum()) < 1e-12:
        return float("nan")
    return float(100.0 * (obs - pred).sum() / obs.sum())


def critical_success_index(
    obs: np.ndarray,
    pred: np.ndarray,
    threshold: float,
) -> dict:
    """
    Flood-event detection metrics.

    Parameters
    ----------
    obs, pred : array-like of float
    threshold : float   Flood detection threshold (e.g. 0.8 × danger_level).

    Returns
    -------
    dict with keys: CSI, POD, FAR, FBI, TP, FP, FN, TN
        CSI = TP / (TP + FP + FN)  Critical Success Index
        POD = TP / (TP + FN)        Probability of Detection
        FAR = FP / (TP + FP)        False Alarm Ratio
        FBI = (TP + FP) / (TP + FN) Frequency Bias
    """
    obs, pred = _clean(obs, pred)
    obs_event  = obs  >= threshold
    pred_event = pred >= threshold

    tp = int(np.sum( obs_event &  pred_event))
    fp = int(np.sum(~obs_event &  pred_event))
    fn = int(np.sum( obs_event & ~pred_event))
    tn = int(np.sum(~obs_event & ~pred_event))

    denom_csi = tp + fp + fn
    denom_pod = tp + fn
    denom_far = tp + fp
    denom_fbi = tp + fn

    return {
        "CSI": tp / denom_csi if denom_csi > 0 else float("nan"),
        "POD": tp / denom_pod if denom_pod > 0 else float("nan"),
        "FAR": fp / denom_far if denom_far > 0 else float("nan"),
        "FBI": (tp + fp) / denom_fbi if denom_fbi > 0 else float("nan"),
        "TP": tp, "FP": fp, "FN": fn, "TN": tn,
    }


def all_metrics(
    obs: np.ndarray,
    pred: np.ndarray,
    threshold: Optional[float] = None,
) -> dict:
    """
    Compute all hydrological metrics in one call.

    Parameters
    ----------
    obs, pred : array-like of float
    threshold : optional float for CSI/POD/FAR computation.

    Returns
    -------
    dict with NSE, KGE, RMSE, MAE, PBIAS, and optionally CSI/POD/FAR.
    """
    result = {
        "NSE":   nash_sutcliffe(obs, pred),
        "KGE":   kling_gupta(obs, pred),
        "RMSE":  rmse(obs, pred),
        "MAE":   mae(obs, pred),
        "PBIAS": pbias(obs, pred),
    }
    if threshold is not None:
        result.update(critical_success_index(obs, pred, threshold))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Per-horizon aggregator
# ─────────────────────────────────────────────────────────────────────────────

def per_horizon_metrics(
    obs: np.ndarray,            # [T, N]  observed at each horizon
    pred: np.ndarray,           # [T, N]  predicted
    horizons: list,
    threshold: Optional[float] = None,
) -> dict:
    """
    Compute metrics for each forecast horizon independently.

    Parameters
    ----------
    obs, pred : np.ndarray  shape [T, H] where H = number of horizons
    horizons  : list of horizon labels (e.g. [1,3,6,12,18,24])
    threshold : optional flood threshold for CSI metrics

    Returns
    -------
    dict  {horizon_hours: {NSE, KGE, RMSE, MAE, ...}}
    """
    results = {}
    for i, h in enumerate(horizons):
        o = obs[:, i] if obs.ndim == 2 else obs
        p = pred[:, i] if pred.ndim == 2 else pred
        results[h] = all_metrics(o, p, threshold)
    return results
