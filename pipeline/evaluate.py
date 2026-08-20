"""
HydroGNN-Net — Evaluation Script

Evaluates the trained model on the held-out TEST set.
Computes multi-horizon hydrological metrics per station and globally.

Usage:
    python pipeline/evaluate.py [--config pipeline/config.yaml] [--checkpoint path/to/best.pt]

Outputs:
    dataset/logs/evaluation_results.json     Full metric breakdown
    dataset/logs/evaluation_report.html      Human-readable HTML report
    dataset/logs/predictions.parquet         Raw predictions vs observations

Scientific Reference:
    Knoben et al. (2019). Technical note: Inherent benchmark or not?
    Comparing Nash-Sutcliffe and Kling-Gupta efficiency scores.
    Hydrology and Earth System Sciences, 23(10), 4323-4331.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import yaml

PIPELINE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PIPELINE_DIR.parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from src.dataset.hydro_dataset import HydroGNNDataset
from src.model.hydrognn_net import HydroGNNNet
from src.utils.logger import get_logger, log_separator
from src.utils.metrics import (
    nash_sutcliffe_efficiency,
    kling_gupta_efficiency,
    root_mean_square_error,
    mean_absolute_error as hydro_mae,
    percent_bias,
)
from torch_geometric.loader import DataLoader

logger = get_logger("evaluate")


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config(path: Path) -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


def resolve_paths(config: dict, project_root: Path) -> dict:
    for key in config["paths"]:
        p = Path(config["paths"][key])
        if not p.is_absolute():
            config["paths"][key] = str(project_root / "pipeline" / p)
    return config


# ---------------------------------------------------------------------------
# Flood detection metrics (CSI / POD / FAR)
# ---------------------------------------------------------------------------

def _binary_flood_metrics(obs: np.ndarray, pred: np.ndarray, threshold: float) -> dict:
    """
    Compute Critical Success Index, Probability of Detection, False Alarm Ratio.

    Parameters
    ----------
    obs, pred : 1-D water level arrays (metres).
    threshold : Flood detection threshold.
    """
    obs_flood  = obs  >= threshold
    pred_flood = pred >= threshold
    hits   = int(np.sum( obs_flood &  pred_flood))
    misses = int(np.sum( obs_flood & ~pred_flood))
    falses = int(np.sum(~obs_flood &  pred_flood))
    denom_csi = hits + misses + falses
    denom_pod = hits + misses
    denom_far = hits + falses
    return {
        "csi": hits / denom_csi if denom_csi > 0 else float("nan"),
        "pod": hits / denom_pod if denom_pod > 0 else float("nan"),
        "far": falses / denom_far if denom_far > 0 else float("nan"),
        "hits": hits, "misses": misses, "false_alarms": falses,
    }


# ---------------------------------------------------------------------------
# Evaluation loop
# ---------------------------------------------------------------------------

@torch.no_grad()
def evaluate_model(model, loader, device, n_nodes):
    """Run inference; return (preds, targets, masks) as [T, N, H] arrays."""
    model.eval()
    preds_l, targets_l, masks_l = [], [], []
    for batch in loader:
        batch  = batch.to(device)
        out    = model(batch)
        pred   = out["pred"].cpu().numpy()        # [B*N, H]
        target = batch.y.cpu().numpy()            # [B*N, H]
        n_per  = batch.num_graphs
        n      = pred.shape[0] // n_per if n_per > 0 else n_nodes
        H      = pred.shape[1]
        preds_l.append(pred.reshape(n_per, n, H))
        targets_l.append(target.reshape(n_per, n, H))
        if hasattr(batch, "mask") and batch.mask is not None:
            masks_l.append(batch.mask.cpu().numpy().reshape(n_per, n))
        else:
            masks_l.append(np.ones((n_per, n), dtype=bool))
    if not preds_l:
        logger.error("No predictions — test dataset is empty.")
        sys.exit(1)
    return (
        np.concatenate(preds_l,   axis=0),
        np.concatenate(targets_l, axis=0),
        np.concatenate(masks_l,   axis=0),
    )


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def compute_metrics(preds, targets, masks, horizons_h, station_ids,
                    flood_threshold_ratio=0.8, danger_levels=None):
    """Compute per-station x per-horizon metrics, plus global and per-horizon aggregates."""
    T, N, H = preds.shape
    results = {"global": {}, "per_station": {}, "per_horizon": {}}
    all_obs, all_pred = [], []

    for n_idx, sid in enumerate(station_ids):
        node_mask = masks[:, n_idx]
        results["per_station"][sid] = {}
        for h_idx, h in enumerate(horizons_h):
            obs_raw  = targets[:, n_idx, h_idx]
            pred_raw = preds[:,   n_idx, h_idx]
            valid = node_mask & np.isfinite(obs_raw) & np.isfinite(pred_raw)
            if valid.sum() < 10:
                logger.warning(f"Station {sid} H+{h}h: only {valid.sum()} valid samples. Skipping.")
                continue
            obs  = obs_raw[valid]
            pred = pred_raw[valid]
            all_obs.extend(obs.tolist())
            all_pred.extend(pred.tolist())
            if danger_levels is not None and n_idx < len(danger_levels):
                fthr = danger_levels[n_idx] * flood_threshold_ratio
            else:
                fthr = float(np.quantile(obs, 0.95))
            m = {
                "nse":   float(nash_sutcliffe_efficiency(obs, pred)),
                "kge":   float(kling_gupta_efficiency(obs, pred)),
                "rmse":  float(root_mean_square_error(obs, pred)),
                "mae":   float(hydro_mae(obs, pred)),
                "pbias": float(percent_bias(obs, pred)),
                "n_valid": int(valid.sum()),
            }
            m.update(_binary_flood_metrics(obs, pred, threshold=fthr))
            results["per_station"][sid][f"H+{h}h"] = m

    # Per-horizon aggregation
    for h_idx, h in enumerate(horizons_h):
        h_obs, h_pred = [], []
        for n_idx in range(N):
            valid = masks[:, n_idx] & np.isfinite(targets[:, n_idx, h_idx]) & np.isfinite(preds[:, n_idx, h_idx])
            h_obs.extend(targets[valid, n_idx, h_idx].tolist())
            h_pred.extend(preds[valid, n_idx, h_idx].tolist())
        if len(h_obs) >= 10:
            o, p = np.array(h_obs), np.array(h_pred)
            results["per_horizon"][f"H+{h}h"] = {
                "nse":   float(nash_sutcliffe_efficiency(o, p)),
                "kge":   float(kling_gupta_efficiency(o, p)),
                "rmse":  float(root_mean_square_error(o, p)),
                "mae":   float(hydro_mae(o, p)),
                "pbias": float(percent_bias(o, p)),
                "n_valid": len(h_obs),
            }

    # Global
    if len(all_obs) >= 10:
        o, p = np.array(all_obs), np.array(all_pred)
        results["global"] = {
            "nse":   float(nash_sutcliffe_efficiency(o, p)),
            "kge":   float(kling_gupta_efficiency(o, p)),
            "rmse":  float(root_mean_square_error(o, p)),
            "mae":   float(hydro_mae(o, p)),
            "pbias": float(percent_bias(o, p)),
            "n_valid": len(all_obs),
        }
    else:
        results["global"] = {"error": "Insufficient valid samples"}
    return results


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

def generate_html_report(results: dict, output_path: Path) -> None:
    rows = []
    for sid, horizons in results.get("per_station", {}).items():
        for hlabel, m in horizons.items():
            rows.append({"Station": sid, "Horizon": hlabel,
                         "NSE": m.get("nse", float("nan")),
                         "KGE": m.get("kge", float("nan")),
                         "RMSE": m.get("rmse", float("nan")),
                         "MAE": m.get("mae", float("nan")),
                         "PBIAS": m.get("pbias", float("nan")),
                         "CSI": m.get("csi", float("nan")),
                         "POD": m.get("pod", float("nan")),
                         "FAR": m.get("far", float("nan")),
                         "N": m.get("n_valid", 0)})
    df = pd.DataFrame(rows)
    table_html = df.to_html(index=False, border=0, classes="tbl",
                             float_format=lambda x: f"{x:.3f}" if isinstance(x, float) and np.isfinite(x) else "n/a")
    g = results.get("global", {})
    grows = "".join(
        f"<tr><td>{k.upper()}</td><td>{v:.4f}</td></tr>"
        for k, v in g.items() if isinstance(v, float) and np.isfinite(v)
    )
    ph = results.get("per_horizon", {})
    ph_rows = "".join(
        f"<tr><td>{hl}</td>"
        + "".join(f"<td>{ph[hl].get(k, float('nan')):.4f}</td>"
                  for k in ["nse", "kge", "rmse", "mae", "pbias"])
        + f"<td>{ph[hl].get('n_valid', 0)}</td></tr>"
        for hl in sorted(ph.keys())
    )
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>HydroGNN-Net Evaluation</title>
<style>
body{{font-family:'Segoe UI',Arial,sans-serif;background:#0f172a;color:#e2e8f0;margin:0;padding:2rem}}
h1{{color:#38bdf8;border-bottom:1px solid #334155;padding-bottom:.5rem}}
h2{{color:#7dd3fc;margin-top:2rem}}
.tbl{{width:100%;border-collapse:collapse;font-size:.83rem}}
.tbl th{{background:#1e293b;color:#94a3b8;padding:.5rem .8rem;text-align:left}}
.tbl td{{padding:.4rem .8rem;border-bottom:1px solid #1e293b}}
.tbl tr:hover td{{background:#1e293b}}
table.sm{{border-collapse:collapse;min-width:220px}}
table.sm td{{padding:.3rem .7rem;border:1px solid #334155}}
p.note{{color:#64748b;font-size:.75rem;margin-top:1.5rem}}
</style></head><body>
<h1>&#128204; HydroGNN-Net — Test Set Evaluation</h1>
<h2>Global Metrics</h2>
<table class="sm">{grows}</table>
<h2>Per-Horizon Metrics (All Stations)</h2>
<table class="sm">
<tr><th>Horizon</th><th>NSE</th><th>KGE</th><th>RMSE (m)</th><th>MAE (m)</th><th>PBIAS %</th><th>N</th></tr>
{ph_rows}</table>
<h2>Per-Station &times; Per-Horizon Breakdown</h2>
{table_html}
<p class="note">NSE &gt; 0.75 = Excellent &nbsp;|&nbsp; 0.5&ndash;0.75 = Good &nbsp;|&nbsp; &lt; 0.5 = Poor (Moriasi et al., 2007)</p>
</body></html>"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    logger.info(f"HTML report written: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="HydroGNN-Net Evaluation")
    parser.add_argument("--config",     default="pipeline/config.yaml")
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    config = resolve_paths(load_config(config_path), PROJECT_ROOT)

    logs_dir   = Path(config["paths"]["logs_dir"])
    models_dir = Path(config["paths"]["models_dir"])
    splits_dir = Path(config["paths"]["splits_dir"])
    logs_dir.mkdir(parents=True, exist_ok=True)

    dev_cfg = config["training"].get("device", "auto")
    device  = torch.device("cuda" if torch.cuda.is_available() else "cpu") if dev_cfg == "auto" else torch.device(dev_cfg)
    logger.info(f"Device: {device}")

    ckpt_path = Path(args.checkpoint) if args.checkpoint else models_dir / "best_model.pt"
    if not ckpt_path.exists():
        logger.error(f"Checkpoint not found: {ckpt_path}\nRun: python pipeline/train.py")
        sys.exit(1)

    model_cfg = config["model"]
    model = HydroGNNNet(
        node_features = model_cfg["node_features"],
        hidden_dim    = model_cfg["hidden_dim"],
        gru_layers    = model_cfg["gru_layers"],
        gat_heads     = model_cfg["gat_heads"],
        gat_layers    = model_cfg["gat_layers"],
        sage_hidden   = model_cfg["sage_hidden"],
        edge_dim      = model_cfg["edge_dim"],
        dropout       = model_cfg["dropout"],
        horizons      = model_cfg["horizons"],
    ).to(device)

    ckpt  = torch.load(ckpt_path, map_location=device, weights_only=False)
    state = ckpt.get("model_state_dict", ckpt)
    model.load_state_dict(state)
    model.eval()
    logger.info(f"Checkpoint loaded: {ckpt_path}")

    # Dataset
    splits_root = splits_dir.parent
    test_ds = HydroGNNDataset(root=str(splits_root), split="test")
    bs = args.batch_size or config["training"]["batch_size"]
    loader = DataLoader(test_ds, batch_size=bs, shuffle=False, num_workers=0)

    station_ids   = [s["id"] for s in config["stations"]]
    horizons_h    = config["model"]["horizons"]
    n_nodes       = len(station_ids)
    danger_levels = [s.get("danger_level_m") for s in config["stations"]]

    log_separator(logger, "Running test-set inference")
    preds, targets, masks = evaluate_model(model, loader, device, n_nodes)

    log_separator(logger, "Computing hydrological metrics")
    results = compute_metrics(
        preds, targets, masks,
        horizons_h=horizons_h,
        station_ids=station_ids,
        flood_threshold_ratio=config["evaluation"].get("flood_threshold_ratio", 0.8),
        danger_levels=danger_levels if all(d is not None for d in danger_levels) else None,
    )

    # Save JSON
    json_out = logs_dir / "evaluation_results.json"
    with open(json_out, "w") as fh:
        json.dump(results, fh, indent=2, default=str)
    logger.info(f"JSON metrics: {json_out}")

    # Save predictions parquet
    T, N, H = preds.shape
    rows = []
    for n_idx, sid in enumerate(station_ids):
        for t_idx in range(T):
            if not masks[t_idx, n_idx]:
                continue
            row = {"station_id": sid, "window_idx": t_idx}
            for h_idx, h in enumerate(horizons_h):
                row[f"obs_H{h}h"]  = float(targets[t_idx, n_idx, h_idx])
                row[f"pred_H{h}h"] = float(preds[t_idx, n_idx, h_idx])
            rows.append(row)
    if rows:
        pd.DataFrame(rows).to_parquet(logs_dir / "predictions.parquet", index=False)
        logger.info(f"Predictions saved: {logs_dir / 'predictions.parquet'}")

    generate_html_report(results, logs_dir / "evaluation_report.html")

    # Console summary
    log_separator(logger, "Evaluation Summary")
    g = results.get("global", {})
    logger.info(f"  Global NSE : {g.get('nse',  float('nan')):.4f}")
    logger.info(f"  Global KGE : {g.get('kge',  float('nan')):.4f}")
    logger.info(f"  Global RMSE: {g.get('rmse', float('nan')):.4f} m")
    logger.info(f"  Global MAE : {g.get('mae',  float('nan')):.4f} m")
    logger.info(f"  Global PBIAS: {g.get('pbias', float('nan')):.2f}%")
    ph = results.get("per_horizon", {})
    if ph:
        logger.info("\n  Per-Horizon NSE:")
        for hlabel in sorted(ph.keys()):
            logger.info(f"    {hlabel:8s}  NSE={ph[hlabel].get('nse', float('nan')):.4f}")
    logger.info(f"\n  Report: {logs_dir / 'evaluation_report.html'}")


if __name__ == "__main__":
    main()
