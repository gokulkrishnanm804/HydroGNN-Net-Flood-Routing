"""
HydroGNN-Net Model Training Script
====================================
Trains the HydroGNN-Net Spatio-Temporal GNN for multi-horizon flood forecasting.

Prerequisites
-------------
1. Run: python pipeline/download_all.py
2. Run: python pipeline/preprocess.py
3. Run: python pipeline/create_dataset.py

Usage
-----
    python pipeline/train.py
    python pipeline/train.py --config pipeline/config.yaml
    python pipeline/train.py --epochs 100
    python pipeline/train.py --resume  # Resume from last checkpoint
    python pipeline/train.py --device cuda
    python pipeline/train.py --batch-size 8

Outputs
-------
    dataset/models/best_model.pt           Best model (lowest val NSE loss)
    dataset/models/last_checkpoint.pt      Last epoch checkpoint
    dataset/logs/training_log.csv          Per-epoch metrics
    dataset/logs/training_curves.png       Loss curves visualization
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

import numpy as np
import torch
import yaml
from torch_geometric.loader import DataLoader

from src.dataset.hydro_dataset import HydroGNNDataset
from src.dataset.splitter import ChronologicalSplitter
from src.model.hydrognn_net import HydroGNNNet, HydroGNNLoss
from src.utils.logger import get_logger, log_separator
from src.utils.metrics import nash_sutcliffe, kling_gupta, rmse, mae, pbias

logger = get_logger("train")


# ─────────────────────────────────────────────────────────────────────────────
# Training loop
# ─────────────────────────────────────────────────────────────────────────────

def train_epoch(
    model: HydroGNNNet,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    criterion: HydroGNNLoss,
    device: torch.device,
    grad_clip: float,
) -> float:
    """Run one training epoch. Returns mean batch loss."""
    model.train()
    total_loss = 0.0
    n_batches  = 0

    for batch in loader:
        batch = batch.to(device)
        optimizer.zero_grad()

        pred, log_var = model(batch.x, batch.edge_index, batch.edge_attr)

        # Mask: only compute loss where we have observed targets
        mask = batch.mask if hasattr(batch, "mask") else None
        loss = criterion(pred, batch.y, log_var=log_var, mask=mask)

        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
        optimizer.step()

        total_loss += loss.item()
        n_batches  += 1

    return total_loss / max(n_batches, 1)


@torch.no_grad()
def evaluate(
    model: HydroGNNNet,
    loader: DataLoader,
    criterion: HydroGNNLoss,
    device: torch.device,
    normalizer=None,
    target_col: str = "water_level_m",
) -> dict:
    """Evaluate model on a DataLoader. Returns metric dict."""
    model.eval()
    all_pred, all_true = [], []
    total_loss = 0.0
    n_batches  = 0

    for batch in loader:
        batch = batch.to(device)
        pred, log_var = model(batch.x, batch.edge_index, batch.edge_attr)
        mask = batch.mask if hasattr(batch, "mask") else None
        loss = criterion(pred, batch.y, log_var=log_var, mask=mask)
        total_loss += loss.item()
        n_batches  += 1

        # Collect 1h horizon predictions for NSE computation
        all_pred.append(pred[:, 0].cpu().numpy())   # 1-hour horizon
        all_true.append(batch.y[:, 0].cpu().numpy())

    pred_arr = np.concatenate(all_pred)
    true_arr = np.concatenate(all_true)

    # Inverse-normalise if scaler available
    if normalizer is not None:
        pred_arr = normalizer.inverse_transform_column(target_col, pred_arr)
        true_arr = normalizer.inverse_transform_column(target_col, true_arr)

    # Filter NaN
    valid = np.isfinite(pred_arr) & np.isfinite(true_arr)
    p, t  = pred_arr[valid], true_arr[valid]

    return {
        "loss":  total_loss / max(n_batches, 1),
        "NSE":   nash_sutcliffe(t, p),
        "KGE":   kling_gupta(t, p),
        "RMSE":  rmse(t, p),
        "MAE":   mae(t, p),
        "PBIAS": pbias(t, p),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Checkpoint utilities
# ─────────────────────────────────────────────────────────────────────────────

def save_checkpoint(
    model: HydroGNNNet,
    optimizer: torch.optim.Optimizer,
    scheduler,
    epoch: int,
    val_metrics: dict,
    cfg: dict,
    path: Path,
) -> None:
    torch.save(
        {
            "epoch":       epoch,
            "model_state": model.state_dict(),
            "optim_state": optimizer.state_dict(),
            "sched_state": scheduler.state_dict() if scheduler else None,
            "val_metrics": val_metrics,
            "model_config": cfg,
        },
        path,
    )


def load_checkpoint(path: Path, model: HydroGNNNet, optimizer, scheduler) -> int:
    """Load checkpoint. Returns the epoch number."""
    ckpt  = torch.load(path, map_location="cpu", weights_only=False)
    model.load_state_dict(ckpt["model_state"])
    optimizer.load_state_dict(ckpt["optim_state"])
    if scheduler and ckpt.get("sched_state"):
        scheduler.load_state_dict(ckpt["sched_state"])
    epoch = ckpt.get("epoch", 0)
    logger.info(f"Resumed from checkpoint (epoch {epoch}): {path}")
    return epoch


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="HydroGNN-Net Training")
    parser.add_argument("--config",     default="pipeline/config.yaml")
    parser.add_argument("--epochs",     type=int,   default=None)
    parser.add_argument("--batch-size", type=int,   default=None)
    parser.add_argument("--lr",         type=float, default=None)
    parser.add_argument("--device",     choices=["auto", "cuda", "cpu"], default=None)
    parser.add_argument("--resume",     action="store_true",
                        help="Resume training from last checkpoint")
    args = parser.parse_args()

    project_root = PIPELINE_DIR.parent
    config_path  = project_root / args.config
    with open(config_path) as fh:
        config = yaml.safe_load(fh)

    # Resolve paths
    for key in config["paths"]:
        p = Path(config["paths"][key])
        if not p.is_absolute():
            config["paths"][key] = str(project_root / "pipeline" / p)

    # CLI overrides
    train_cfg = config["training"]
    if args.epochs:     train_cfg["epochs"]     = args.epochs
    if args.batch_size: train_cfg["batch_size"] = args.batch_size
    if args.lr:         train_cfg["lr"]          = args.lr
    if args.device:     train_cfg["device"]      = args.device

    # ── Device ────────────────────────────────────────────────────────────
    dev_str = train_cfg.get("device", "auto")
    if dev_str == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(dev_str)
    logger.info(f"Device: {device}")

    # ── Reproducibility ───────────────────────────────────────────────────
    seed = int(train_cfg.get("seed", 42))
    torch.manual_seed(seed)
    np.random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    # Full determinism for reproducibility (slight performance cost)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark     = False
    os.environ["PYTHONHASHSEED"]        = str(seed)

    def _worker_init(worker_id: int) -> None:
        np.random.seed(seed + worker_id)
        import random; random.seed(seed + worker_id)

    # ── Dataset ───────────────────────────────────────────────────────────
    splits_dir = Path(config["paths"]["splits_dir"])
    root_dir   = splits_dir.parent

    log_separator(logger, "Loading Datasets")
    try:
        train_ds = HydroGNNDataset(str(root_dir), split="train")
        val_ds   = HydroGNNDataset(str(root_dir), split="val")
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)

    bs = int(train_cfg["batch_size"])
    train_loader = DataLoader(
        train_ds, batch_size=bs, shuffle=True,
        num_workers=0, pin_memory=(device.type == "cuda"),
        worker_init_fn=_worker_init,
    )
    val_loader = DataLoader(
        val_ds, batch_size=bs, shuffle=False,
        num_workers=0, pin_memory=(device.type == "cuda"),
    )

    logger.info(f"Train: {len(train_ds)} samples | Val: {len(val_ds)} samples")

    # ── Model ─────────────────────────────────────────────────────────────
    log_separator(logger, "Building HydroGNN-Net")
    model = HydroGNNNet.from_config(config["model"]).to(device)
    logger.info(f"Parameters: {model.count_parameters():,}")

    # ── Optimiser & Scheduler ─────────────────────────────────────────────
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(train_cfg["lr"]),
        weight_decay=float(train_cfg["weight_decay"]),
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer,
        T_max=int(train_cfg.get("scheduler_T_max", 100)),
        eta_min=float(train_cfg["lr"]) * 0.01,
    )

    # ── Loss ──────────────────────────────────────────────────────────────
    criterion = HydroGNNLoss(
        mse_weight=float(train_cfg.get("mse_weight", 1.0)),
        nse_weight=float(train_cfg.get("nse_weight", 0.3)),
        physics_weight=float(train_cfg.get("physics_weight", 0.1)),
    )

    # ── Resume ────────────────────────────────────────────────────────────
    models_dir    = Path(config["paths"]["models_dir"])
    models_dir.mkdir(parents=True, exist_ok=True)
    ckpt_dir      = Path(config["paths"]["checkpoints_dir"])
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    last_ckpt     = models_dir / "last_checkpoint.pt"
    best_ckpt     = models_dir / "best_model.pt"

    start_epoch  = 0
    best_val_nse = float("-inf")
    patience_ctr = 0

    if args.resume and last_ckpt.exists():
        start_epoch = load_checkpoint(last_ckpt, model, optimizer, scheduler)

    # ── Training log ──────────────────────────────────────────────────────
    logs_dir  = Path(config["paths"]["logs_dir"])
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path  = logs_dir / "training_log.csv"
    LOG_COLS  = ["epoch", "train_loss", "val_loss", "val_NSE", "val_KGE",
                 "val_RMSE", "val_MAE", "val_PBIAS", "lr", "duration_s"]
    if not log_path.exists():
        with open(log_path, "w", newline="") as fh:
            csv.DictWriter(fh, fieldnames=LOG_COLS).writeheader()

    # ── Main training loop ────────────────────────────────────────────────
    n_epochs  = int(train_cfg["epochs"])
    patience  = int(train_cfg.get("patience", 15))
    min_delta = float(train_cfg.get("min_delta", 0.001))
    grad_clip = float(train_cfg.get("grad_clip", 1.0))

    log_separator(logger, f"Training HydroGNN-Net ({device})")

    for epoch in range(start_epoch + 1, n_epochs + 1):
        t_start = time.monotonic()

        train_loss = train_epoch(model, train_loader, optimizer, criterion,
                                  device, grad_clip)
        val_metrics = evaluate(model, val_loader, criterion, device)
        scheduler.step()

        elapsed = time.monotonic() - t_start
        cur_lr  = optimizer.param_groups[0]["lr"]
        val_nse = val_metrics["NSE"]

        # Logging
        logger.info(
            f"Epoch {epoch:03d}/{n_epochs} | "
            f"Train: {train_loss:.4f} | "
            f"Val: {val_metrics['loss']:.4f} | "
            f"NSE: {val_nse:.4f} | "
            f"KGE: {val_metrics['KGE']:.4f} | "
            f"RMSE: {val_metrics['RMSE']:.3f}m | "
            f"LR: {cur_lr:.2e} | "
            f"{elapsed:.1f}s"
        )

        row = {
            "epoch":      epoch,
            "train_loss": round(train_loss, 6),
            "val_loss":   round(val_metrics["loss"], 6),
            "val_NSE":    round(val_nse, 6) if np.isfinite(val_nse) else "",
            "val_KGE":    round(val_metrics["KGE"], 6),
            "val_RMSE":   round(val_metrics["RMSE"], 4),
            "val_MAE":    round(val_metrics["MAE"], 4),
            "val_PBIAS":  round(val_metrics["PBIAS"], 4),
            "lr":         cur_lr,
            "duration_s": round(elapsed, 2),
        }
        with open(log_path, "a", newline="") as fh:
            csv.DictWriter(fh, fieldnames=LOG_COLS).writerow(row)

        # ── Save checkpoints ─────────────────────────────────────────────
        save_checkpoint(model, optimizer, scheduler, epoch, val_metrics,
                        config["model"], last_ckpt)

        # Periodic epoch checkpoints
        if epoch % 10 == 0:
            ep_ckpt = ckpt_dir / f"epoch_{epoch:04d}.pt"
            save_checkpoint(model, optimizer, scheduler, epoch, val_metrics,
                            config["model"], ep_ckpt)

        # ── Early stopping ────────────────────────────────────────────────
        if np.isfinite(val_nse) and val_nse > best_val_nse + min_delta:
            best_val_nse = val_nse
            patience_ctr = 0
            save_checkpoint(model, optimizer, scheduler, epoch, val_metrics,
                            config["model"], best_ckpt)
            logger.info(f"  → New best NSE: {best_val_nse:.4f}  (saved to {best_ckpt.name})")
        else:
            patience_ctr += 1
            if patience_ctr >= patience:
                logger.info(
                    f"Early stopping triggered at epoch {epoch}. "
                    f"Best val NSE = {best_val_nse:.4f}"
                )
                break

    # ── Final report ──────────────────────────────────────────────────────
    log_separator(logger, "Training Complete")
    logger.info(f"Best validation NSE : {best_val_nse:.4f}")
    logger.info(f"Best model saved    : {best_ckpt}")
    logger.info(f"Training log        : {log_path}")
    logger.info("")
    logger.info("Next steps:")
    logger.info("  python pipeline/evaluate.py   — Evaluate on test set")
    logger.info("  python pipeline/export_model.py — Export to ONNX for inference")


if __name__ == "__main__":
    main()
