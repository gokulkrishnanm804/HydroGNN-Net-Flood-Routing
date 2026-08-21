"""
HydroGNN-Net PyTorch Geometric Dataset
========================================
Compatible with HydroGNN_Datasets/pytorch/ split files where each .pt
file contains a Python list of dicts with keys:
    x, x_seq, edge_index, edge_attr, y, y_mask, timestamp, stations

The loader converts each dict into a torch_geometric.data.Data object:
    data.x          <- sample["x_seq"]    [N, T, F]
    data.edge_index <- sample["edge_index"]
    data.edge_attr  <- sample["edge_attr"]
    data.y          <- sample["y"]        [N, H]
    data.y_mask     <- sample["y_mask"]   [N, H]
    data.timestamp  <- sample["timestamp"]  (metadata)
    data.stations   <- sample["stations"]   (metadata)

Directory layout (two modes, auto-detected):
  Mode A  - direct pytorch dir (preferred):
            root = ".../HydroGNN_Datasets/pytorch"
            files at: root/train.pt, root/val.pt, root/test.pt

  Mode B  - legacy splits subdir:
            root = ".../dataset"
            files at: root/splits/train.pt, ...

Note on PyG 2.5+
-----------------
torch_geometric >= 2.5 changed files_exist([]) -> False, which causes
_download() to fire even when raw_file_names is empty.  We override the
private _download() and _process() hooks directly so PyG never tries to
fetch or re-process anything.
"""
from __future__ import annotations

from pathlib import Path

import torch
from torch_geometric.data import Data, InMemoryDataset

from src.utils.logger import get_logger

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _dict_to_data(sample: dict) -> Data:
    """Convert a raw dict sample into a torch_geometric Data object."""
    # Prefer x_seq (the full lookback window); fall back to x
    x = sample.get("x_seq", sample.get("x"))
    if x is None:
        raise KeyError("Sample dict has neither 'x_seq' nor 'x'.")

    data = Data(
        x          = x.float(),
        edge_index = sample["edge_index"].long(),
        edge_attr  = sample["edge_attr"].float(),
        y          = sample["y"].float(),
        y_mask     = sample.get("y_mask"),
    )
    # Non-tensor metadata — stored as plain Python attributes
    if "timestamp" in sample:
        data.timestamp = sample["timestamp"]
    if "stations" in sample:
        data.stations = sample["stations"]
    return data


def _resolve_split_path(root: str, split: str) -> Path:
    """Return the .pt file path, trying Mode A then Mode B."""
    root_p = Path(root)
    mode_a = root_p / f"{split}.pt"
    if mode_a.exists():
        return mode_a
    mode_b = root_p / "splits" / f"{split}.pt"
    if mode_b.exists():
        return mode_b
    raise FileNotFoundError(
        f"Dataset split file not found.\n"
        f"  Tried Mode A: {mode_a}\n"
        f"  Tried Mode B: {mode_b}\n\n"
        "Set splits_dir in config.yaml to the directory containing "
        "train.pt / val.pt / test.pt  (e.g. HydroGNN_Datasets/pytorch/)."
    )


# --------------------------------------------------------------------------- #
# Dataset class
# --------------------------------------------------------------------------- #

class HydroGNNDataset(InMemoryDataset):
    """
    InMemoryDataset wrapper for HydroGNN-Net pre-built split files.

    Accepts both dict-based samples (HydroGNN_Datasets/pytorch/*.pt) and
    legacy torch_geometric.data.Data list files.

    Parameters
    ----------
    root  : Directory that directly contains train/val/test .pt files,
            OR a parent directory whose 'splits/' sub-folder contains them.
    split : One of 'train', 'val', 'test'.
    """

    VALID_SPLITS = ("train", "val", "test")

    def __init__(
        self,
        root:          str,
        split:         str = "train",
        transform      = None,
        pre_transform  = None,
    ) -> None:
        assert split in self.VALID_SPLITS, (
            f"split must be one of {self.VALID_SPLITS}, got '{split}'"
        )
        self.split = split

        # super().__init__() would call _download() / _process(); we bypass
        # those safely by overriding them below, then trigger super init.
        super().__init__(root, transform, pre_transform)

        # ----- Load split file -----
        split_path = _resolve_split_path(root, split)
        logger.info(f"Loading {split} split from {split_path} ...")

        raw_list = torch.load(split_path, weights_only=False)

        if not isinstance(raw_list, list) or len(raw_list) == 0:
            raise ValueError(
                f"{split}.pt appears empty or corrupt: {split_path}"
            )

        # Convert dicts -> Data if necessary
        if isinstance(raw_list[0], dict):
            logger.info(
                f"  Converting {len(raw_list):,} dict samples -> "
                "PyG Data objects ..."
            )
            data_list = [_dict_to_data(s) for s in raw_list]
        else:
            data_list = raw_list          # already Data objects

        self.data, self.slices = self.collate(data_list)
        logger.info(f"Loaded {len(data_list):,} {split} samples.")

    # ----------------------------------------------------------------------- #
    # Override PyG's private hooks so it never tries to download / process
    # (needed for PyG >= 2.5 where files_exist([]) returns False)
    # ----------------------------------------------------------------------- #

    def _download(self) -> None:
        # No raw files to download — all data is pre-built.
        pass

    def _process(self) -> None:
        # No processing step — data loaded directly in __init__.
        pass

    # These public hooks are never reached, but keep them for safety:
    @property
    def raw_file_names(self):
        return []

    @property
    def processed_file_names(self):
        return []

    def download(self) -> None:
        pass

    def process(self) -> None:
        pass

    # ----------------------------------------------------------------------- #
    # Utilities
    # ----------------------------------------------------------------------- #

    def len(self) -> int:
        if self.slices is None:
            return 0
        first_key = next(iter(self.slices))
        return int(self.slices[first_key].numel()) - 1

    def __repr__(self) -> str:
        return f"HydroGNNDataset(split={self.split!r}, n={len(self)})"
