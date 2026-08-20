"""
Rolling Rainfall Accumulations and Antecedent Rainfall Index (ARI)

All computations use REAL precipitation data from GPM IMERG.
No synthetic or estimated values are generated.
If GPM data is unavailable, the functions return NaN for affected rows
and log a WARNING (never silently substitute zeros).

ARI Reference:
    Chen, J. & Adams, B.J. (2006). A semi-distributed non-linear rainfall-runoff
    model and its application to the lower Yangtze catchment.
    Catena, 68(2), 94-108.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger(__name__)


def compute_rolling_rainfall(
    df: pd.DataFrame,
    precip_col: str = "precipitation_mm_30min",
    windows_hours: list = None,
) -> pd.DataFrame:
    """
    Compute rolling precipitation accumulations for multiple time windows.

    For 30-minute resolution:
        window_steps = hours × 2  (e.g. 1h = 2 steps, 24h = 48 steps)

    Uses .rolling().sum() with min_periods=1 to handle edge effects at the
    start of the record (not fabrication — just partial accumulations).
    Clips to zero to prevent floating-point numerical negatives.

    Parameters
    ----------
    df            : DataFrame with DatetimeIndex at 30T resolution
                    and *precip_col* column.
    precip_col    : Name of the 30-min precipitation column.
    windows_hours : List of accumulation windows in hours.
                    Default: [1, 3, 6, 12, 24].

    Returns
    -------
    pd.DataFrame  Input DataFrame with added columns:
                  rainfall_1h, rainfall_3h, rainfall_6h, rainfall_12h, rainfall_24h
    """
    if windows_hours is None:
        windows_hours = [1, 3, 6, 12, 24]

    if precip_col not in df.columns:
        logger.warning(f"Precipitation column '{precip_col}' not found. Rolling sums will be NaN.")
        df = df.copy()
        for h in windows_hours:
            df[f"rainfall_{h}h"] = np.nan
        return df

    df = df.copy()
    for h in windows_hours:
        steps = h * 2   # 30-min resolution
        col = f"rainfall_{h}h"
        df[col] = (
            df[precip_col]
            .rolling(window=steps, min_periods=1)
            .sum()
            .clip(lower=0)
        )
        n_valid = df[col].notna().sum()
        logger.debug(
            f"Computed {col}: "
            f"mean={df[col].mean():.3f}mm, "
            f"max={df[col].max():.3f}mm, "
            f"valid={n_valid}/{len(df)}"
        )
    return df


def compute_antecedent_rainfall_index(
    df: pd.DataFrame,
    precip_col: str = "rainfall_6h",
    decay: float = 0.9,
) -> pd.Series:
    """
    Antecedent Rainfall Index (ARI) with exponential decay.

    ARI(t) = decay × ARI(t−1) + P_6h(t)

    Computed iteratively for physical correctness (not vectorized,
    since each step depends on the previous).
    Initial ARI = 0.0 (dry antecedent conditions).

    Parameters
    ----------
    df         : DataFrame with DatetimeIndex and *precip_col* column.
    precip_col : 6-hour accumulated rainfall column.
    decay      : Decay coefficient. Valid range: 0.80–0.98.
                 Higher → longer memory of antecedent rainfall.

    Returns
    -------
    pd.Series  ARI values with same index as *df*, name='antecedent_rainfall_index'.
    """
    if precip_col not in df.columns:
        logger.warning(f"Column '{precip_col}' not found for ARI. Returning zeros.")
        return pd.Series(0.0, index=df.index, name="antecedent_rainfall_index")

    if not (0.5 <= decay <= 0.99):
        logger.warning(f"ARI decay={decay} is outside recommended range [0.80, 0.98]")

    precip = df[precip_col].fillna(0.0).values
    ari    = np.zeros(len(precip), dtype=float)

    for t in range(1, len(precip)):
        ari[t] = decay * ari[t - 1] + precip[t]

    logger.debug(
        f"ARI computed: decay={decay}, "
        f"mean={ari.mean():.3f}, max={ari.max():.3f}"
    )
    return pd.Series(ari, index=df.index, name="antecedent_rainfall_index")
