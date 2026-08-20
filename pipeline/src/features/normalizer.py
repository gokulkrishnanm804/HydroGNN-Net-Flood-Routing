"""
Feature normalizer for HydroGNN-Net.

CRITICAL: Statistics are computed ONLY on the training split.
Test and validation splits must NEVER influence scaling parameters.
This prevents data leakage that would invalidate evaluation metrics.

Reference:
    Hastie, T., Tibshirani, R. & Friedman, J. (2009).
    The Elements of Statistical Learning (2nd ed.), Section 2.3.
    Springer. https://doi.org/10.1007/978-0-387-84858-7
"""
from __future__ import annotations

import json
import numpy as np
import pandas as pd
from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger(__name__)


class FeatureNormalizer:
    """
    Normalizes feature columns using statistics from the training split ONLY.

    Methods
    -------
    'robust'   : (x − median) / IQR   — robust to outliers (default)
    'standard' : (x − mean) / std     — standard z-score
    'minmax'   : (x − min) / (max−min) — [0,1] range

    Usage
    -----
        norm = FeatureNormalizer('robust')
        norm.fit(full_df, feature_cols, train_end_idx=n_train)
        train_df_norm = norm.transform(train_df)
        val_df_norm   = norm.transform(val_df)    # uses SAME stats from training
        norm.save(Path('dataset/models/normalizer.json'))
    """

    VALID_METHODS = ("robust", "standard", "minmax")

    def __init__(self, method: str = "robust") -> None:
        if method not in self.VALID_METHODS:
            raise ValueError(f"method must be one of {self.VALID_METHODS}, got '{method}'")
        self.method  = method
        self._stats: dict = {}    # {feature: {center: float, scale: float}}
        self._fitted = False

    # ------------------------------------------------------------------ #
    # Fit
    # ------------------------------------------------------------------ #

    def fit(
        self,
        df: pd.DataFrame,
        feature_cols: list,
        train_end_idx: int,
    ) -> "FeatureNormalizer":
        """
        Fit scaler using ONLY the first *train_end_idx* rows.

        Parameters
        ----------
        df            : Full feature DataFrame (train + val + test).
        feature_cols  : List of column names to normalize.
        train_end_idx : Last row index of training data (exclusive).
                        Example: if 70% train and total rows=10000, pass 7000.
        """
        if train_end_idx <= 0:
            raise ValueError("train_end_idx must be positive")

        train_df = df.iloc[:train_end_idx]

        for col in feature_cols:
            if col not in train_df.columns:
                logger.warning(f"Feature '{col}' not in DataFrame; skipping normalization")
                self._stats[col] = {"center": 0.0, "scale": 1.0}
                continue

            vals = train_df[col].dropna().values.astype(float)
            if len(vals) == 0:
                logger.warning(f"No valid training values for '{col}'; using center=0 scale=1")
                self._stats[col] = {"center": 0.0, "scale": 1.0}
                continue

            if self.method == "robust":
                center = float(np.median(vals))
                q75, q25 = np.percentile(vals, [75, 25])
                scale  = float(q75 - q25)
            elif self.method == "standard":
                center = float(np.mean(vals))
                scale  = float(np.std(vals))
            else:  # minmax
                center = float(np.min(vals))
                scale  = float(np.max(vals) - np.min(vals))

            if scale < 1e-9:
                logger.warning(f"Near-zero scale for '{col}' ({scale:.2e}); using scale=1.0")
                scale = 1.0

            self._stats[col] = {"center": center, "scale": scale}

        self._fitted = True
        logger.info(
            f"FeatureNormalizer fitted ({self.method}) on {train_end_idx} "
            f"training rows, {len(feature_cols)} features"
        )
        return self

    # ------------------------------------------------------------------ #
    # Transform / Inverse
    # ------------------------------------------------------------------ #

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply normalization to a DataFrame (in-place copy)."""
        if not self._fitted:
            raise RuntimeError("Call fit() before transform()")
        df = df.copy()
        for col, stat in self._stats.items():
            if col in df.columns:
                df[col] = (df[col] - stat["center"]) / stat["scale"]
        return df

    def inverse_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Reverse normalization of a DataFrame."""
        if not self._fitted:
            raise RuntimeError("Call fit() before inverse_transform()")
        df = df.copy()
        for col, stat in self._stats.items():
            if col in df.columns:
                df[col] = df[col] * stat["scale"] + stat["center"]
        return df

    def inverse_transform_column(self, col: str, values: np.ndarray) -> np.ndarray:
        """Inverse-transform a single feature column's numpy array."""
        if not self._fitted:
            raise RuntimeError("Call fit() before inverse_transform_column()")
        if col not in self._stats:
            logger.warning(f"Column '{col}' not in normalizer stats; returning as-is")
            return values
        stat = self._stats[col]
        return np.asarray(values) * stat["scale"] + stat["center"]

    def transform_array(self, arr: np.ndarray, feature_names: list) -> np.ndarray:
        """
        Normalize a 2D numpy array [N, F] using the provided feature name order.

        Parameters
        ----------
        arr           : [N, F] float array.
        feature_names : List of F feature names matching columns of arr.
        """
        if not self._fitted:
            raise RuntimeError("Call fit() before transform_array()")
        out = arr.copy().astype(float)
        for i, col in enumerate(feature_names):
            if col in self._stats:
                stat = self._stats[col]
                out[:, i] = (out[:, i] - stat["center"]) / stat["scale"]
        return out

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    def save(self, path: Path) -> None:
        """Save normalizer stats as JSON."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"method": self.method, "stats": self._stats}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        logger.info(f"Normalizer saved: {path}")

    def load(self, path: Path) -> "FeatureNormalizer":
        """Load normalizer stats from JSON."""
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        self.method  = payload["method"]
        self._stats  = payload["stats"]
        self._fitted = True
        logger.info(f"Normalizer loaded: {path} ({len(self._stats)} features, method={self.method})")
        return self

    def get_stats(self) -> dict:
        """Return a copy of the scaling statistics."""
        return {k: dict(v) for k, v in self._stats.items()}
