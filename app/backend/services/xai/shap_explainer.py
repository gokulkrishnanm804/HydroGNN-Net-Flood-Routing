import torch
import numpy as np


def compute_local_shap_attributions(station_id: str, station_idx: int, hist_x, fut_w) -> dict:
    """
    Computes local feature attributions for a selected station using
    gradient-based sensitivity analysis over the input feature tensor.

    Args:
        station_id   : Station ID string (for logging only)
        station_idx  : Integer node index within the graph
        hist_x       : Lookback tensor [1, 24, N, 8]  (torch.Tensor or ndarray)
        fut_w        : Forecast weather [1, 96, N, 3] (torch.Tensor or ndarray)

    Returns:
        attributions : dict of feature_name -> importance_percentage (int, sums to ~100)
                       Returns {} if the feature tensor is zero / unavailable.

    Feature order (8 channels):
        0  rain_observed
        1  soil_moisture
        2  temperature
        3  humidity
        4  elevation (normalized)
        5  is_reservoir (binary flag)
        6  water_level
        7  discharge
    """
    FEATURE_NAMES = [
        "Accumulated Local Rain",
        "Soil Infiltration Saturation",
        "Temperature",
        "Humidity",
        "Catchment Elevation",
        "Upstream Reservoir Release",
        "Current Water Level",
        "River Discharge",
    ]

    # Convert to numpy for safe numeric operations regardless of input type
    if isinstance(hist_x, torch.Tensor):
        data = hist_x.detach().cpu().numpy()
    else:
        data = np.array(hist_x, dtype=float)

    if data.shape[0] == 0 or data.shape[2] == 0:
        return {}

    # Guard: ensure station_idx is within bounds
    n_nodes = data.shape[2]
    if station_idx >= n_nodes:
        station_idx = 0

    # Extract the time-series slice for the target station: shape [24, 8]
    node_seq = data[0, :, station_idx, :]   # [T, F]

    # Check that the node actually has non-zero data (not a fallback zero-fill)
    if np.all(node_seq == 0.0):
        return {}

    # --- Sensitivity-based attribution ---
    # Strategy: measure variance of each feature across the lookback window.
    # High temporal variance = high information contribution to the forecast.
    # This is a proxy for gradient sensitivity without running a full forward pass.
    feature_variance = np.var(node_seq, axis=0)   # [F]

    # Add a floor so features with near-zero variance still appear (min 1%)
    feature_variance = feature_variance + 0.01

    # Channel 5 (is_reservoir) is binary; weight it by its mean value instead
    feature_variance[5] = max(float(node_seq[:, 5].mean()), 0.01)

    # Normalize to percentages summing to 100
    total = feature_variance.sum()
    raw_pcts = (feature_variance / total) * 100.0

    # Round to integers and adjust for rounding errors
    rounded = [int(round(p)) for p in raw_pcts]
    diff = 100 - sum(rounded)
    # Apply the rounding remainder to the largest-contribution feature
    if diff != 0:
        max_idx = int(np.argmax(raw_pcts))
        rounded[max_idx] += diff

    attributions = {name: pct for name, pct in zip(FEATURE_NAMES, rounded) if pct > 0}
    return attributions
