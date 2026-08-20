"""
HydroGNN-Net PyTorch Geometric Dataset

Works with pre-built .pt files created by: python pipeline/create_dataset.py

Directory structure expected:
    {root}/splits/train.pt
    {root}/splits/val.pt
    {root}/splits/test.pt
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import torch
from torch_geometric.data import Data, InMemoryDataset

from src.utils.logger import get_logger

logger = get_logger(__name__)


class HydroGNNDataset(InMemoryDataset):
    """
    InMemoryDataset wrapper for HydroGNN-Net split files.

    Each split file contains a Python list of torch_geometric.data.Data objects,
    where each Data object represents one sliding-window sample:

        data.x          [N_nodes, T_lookback, F_features]  float32
        data.y          [N_nodes, H_horizons]               float32
        data.edge_index [2, E]                              long
        data.edge_attr  [E, 4]                              float32
        data.time_index scalar Unix timestamp               long
        data.mask       [N_nodes]                           bool (optional)

    Parameters
    ----------
    root  : Directory containing the 'splits/' subdirectory.
    split : One of 'train', 'val', 'test'.
    """

    VALID_SPLITS = ("train", "val", "test")

    def __init__(
        self,
        root:          str,
        split:         str = "train",
        transform=None,
        pre_transform=None,
    ) -> None:
        assert split in self.VALID_SPLITS, (
            f"split must be one of {self.VALID_SPLITS}, got '{split}'"
        )
        self.split = split
        super().__init__(root, transform, pre_transform)

        split_path = Path(root) / "splits" / f"{split}.pt"
        if not split_path.exists():
            raise FileNotFoundError(
                f"Dataset split file not found: {split_path}\n"
                "\n"
                "Run the dataset creation script first:\n"
                "    python pipeline/create_dataset.py\n"
                "\n"
                "This requires preprocessed data from:\n"
                "    python pipeline/download_all.py\n"
                "    python pipeline/preprocess.py\n"
            )

        logger.info(f"Loading {split} split from {split_path}…")
        data_list = torch.load(split_path, weights_only=False)

        if not isinstance(data_list, list) or len(data_list) == 0:
            raise ValueError(
                f"{split}.pt appears empty or corrupt. "
                "Re-run: python pipeline/create_dataset.py"
            )

        self.data, self.slices = self.collate(data_list)
        logger.info(f"Loaded {len(data_list)} {split} samples")

    @property
    def raw_file_names(self):
        return []

    @property
    def processed_file_names(self):
        # Return only THIS split's file so PyG doesn't check for other splits
        # when loading a single split (e.g., loading 'val' shouldn't require 'train').
        return [f"{self.split}.pt"]

    def download(self) -> None:
        raise RuntimeError(
            "This dataset does not auto-download raw data.\n"
            "Run: python pipeline/create_dataset.py"
        )

    def process(self) -> None:
        pass  # Data is already processed by create_dataset.py

    def len(self) -> int:
        if self.slices is None:
            return 0
        # InMemoryDataset: number of graphs = len of any slice tensor - 1
        first_key = next(iter(self.slices))
        return int(self.slices[first_key].numel()) - 1

    # get() is intentionally not overridden — InMemoryDataset.get() is inherited.
    # Overriding with a simple super() call is dead code.

    def __repr__(self) -> str:
        return f"HydroGNNDataset(split={self.split}, n={len(self)})"
