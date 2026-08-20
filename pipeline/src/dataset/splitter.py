"""
Chronological Data Splitter for HydroGNN-Net

TIME IS NEVER SHUFFLED.

Split is always: first 70% train, next 15% val, last 15% test.
This is the only scientifically valid split for time series forecasting.

Shuffling would create data leakage — future data leaking into training —
which would produce artificially inflated evaluation metrics.

Reference:
    Hyndman, R.J. & Athanasopoulos, G. (2021). Forecasting: Principles and Practice
    (3rd ed.), Chapter 3.4 — Training and test sets. OTexts. https://otexts.com/fpp3/
"""
from __future__ import annotations

from typing import List, Tuple

from src.utils.logger import get_logger

logger = get_logger(__name__)


class ChronologicalSplitter:
    """
    Splits a list of chronologically ordered Data objects into train/val/test.

    Parameters
    ----------
    train_ratio : Fraction for training (default 0.70).
    val_ratio   : Fraction for validation (default 0.15).
    test_ratio  : Fraction for test (default 0.15).

    All three must sum to 1.0 (checked at init).
    """

    def __init__(
        self,
        train_ratio: float = 0.70,
        val_ratio:   float = 0.15,
        test_ratio:  float = 0.15,
    ) -> None:
        total = train_ratio + val_ratio + test_ratio
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"Split ratios must sum to 1.0, got {total:.6f} "
                f"(train={train_ratio}, val={val_ratio}, test={test_ratio})"
            )
        self.train_ratio = train_ratio
        self.val_ratio   = val_ratio
        self.test_ratio  = test_ratio

    # ------------------------------------------------------------------ #
    # Index computation
    # ------------------------------------------------------------------ #

    def split_indices(self, n: int) -> Tuple[range, range, range]:
        """
        Compute chronological split index ranges.

        Parameters
        ----------
        n : Total number of samples.

        Returns
        -------
        (train_range, val_range, test_range)
        """
        train_end = int(n * self.train_ratio)
        val_end   = int(n * (self.train_ratio + self.val_ratio))

        # Ensure at least 1 sample per split
        train_end = max(1, min(train_end, n - 2))
        val_end   = max(train_end + 1, min(val_end, n - 1))

        return (
            range(0,         train_end),
            range(train_end, val_end),
            range(val_end,   n),
        )

    # ------------------------------------------------------------------ #
    # Split
    # ------------------------------------------------------------------ #

    def split(self, data_list: list) -> Tuple[list, list, list]:
        """
        Split a list of Data objects chronologically.

        Parameters
        ----------
        data_list : Ordered list of PyG Data objects (time-sorted).

        Returns
        -------
        (train_list, val_list, test_list)
        """
        n = len(data_list)
        if n < 3:
            raise ValueError(f"Need at least 3 samples for split, got {n}")

        train_idx, val_idx, test_idx = self.split_indices(n)

        train = [data_list[i] for i in train_idx]
        val   = [data_list[i] for i in val_idx]
        test  = [data_list[i] for i in test_idx]

        logger.info(
            f"Chronological split (N={n}): "
            f"train={len(train)} ({len(train)/n*100:.1f}%), "
            f"val={len(val)} ({len(val)/n*100:.1f}%), "
            f"test={len(test)} ({len(test)/n*100:.1f}%)"
        )
        return train, val, test

    # ------------------------------------------------------------------ #
    # Report
    # ------------------------------------------------------------------ #

    def report(self, train: list, val: list, test: list) -> dict:
        """Return a summary dict for logging."""
        total = len(train) + len(val) + len(test)
        return {
            "train_size": len(train),
            "val_size":   len(val),
            "test_size":  len(test),
            "total_size": total,
            "train_pct":  len(train) / total * 100,
            "val_pct":    len(val)   / total * 100,
            "test_pct":   len(test)  / total * 100,
        }
