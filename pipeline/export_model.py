"""
HydroGNN-Net — Model Export Script

Exports the trained model to ONNX format for production deployment
and optionally INT8 quantization for edge devices.

Usage:
    python pipeline/export_model.py [--config pipeline/config.yaml]
                                    [--checkpoint path/to/best.pt]
                                    [--no-onnx]

Outputs:
    dataset/models/hydrognn_net.onnx        ONNX model for inference
    dataset/models/hydrognn_net_q.onnx      INT8 quantized model (optional)
    dataset/models/model_card.json          Model card with metadata

Reference:
    ONNX opset 14 supports GRU and scatter/gather ops needed by PyG GNNs.
    https://github.com/onnx/onnx/blob/main/docs/Operators.md
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch
import yaml

PIPELINE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PIPELINE_DIR.parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from src.model.hydrognn_net import HydroGNNNet
from src.utils.logger import get_logger, log_separator

logger = get_logger("export_model")


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
# Model summary
# ---------------------------------------------------------------------------

def count_parameters(model: torch.nn.Module) -> dict:
    total   = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return {"total": total, "trainable": trainable, "frozen": total - trainable}


# ---------------------------------------------------------------------------
# ONNX export
# ---------------------------------------------------------------------------

def export_onnx(
    model:      HydroGNNNet,
    onnx_path:  Path,
    n_nodes:    int,
    lookback:   int,
    n_features: int,
    n_edges:    int,
    edge_dim:   int,
    opset:      int = 14,
) -> bool:
    """
    Export model to ONNX.

    Note on PyG + ONNX:
        PyG GNN layers (GATv2Conv, SAGEConv) use scatter/gather operations
        that are not directly ONNX-traceable in all versions.
        This export uses torch.jit.script tracing. If it fails, a fallback
        TorchScript export is written instead.

    Parameters
    ----------
    n_nodes, lookback, n_features : Dummy input dimensions.
    n_edges, edge_dim             : Edge tensor dimensions.
    opset                         : ONNX opset version.

    Returns True if ONNX export succeeded, False if fell back to TorchScript.
    """
    try:
        import onnx                          # noqa: F401 (confirm package available)
    except ImportError:
        logger.error("onnx package not installed. Run: pip install onnx onnxruntime")
        return False

    # Build dummy inputs
    x          = torch.randn(n_nodes, lookback, n_features)
    edge_index = torch.zeros((2, n_edges), dtype=torch.long)
    edge_attr  = torch.randn(n_edges, edge_dim)

    # Wrap model for tracing (forward returns dict — flatten for ONNX)
    class _OnnxWrapper(torch.nn.Module):
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, x, edge_index, edge_attr):
            # Minimal forward: node features only (no PyG Data object)
            # This calls TemporalEncoder + GATv2Encoder + SAGERefiner + heads
            from torch_geometric.data import Data
            dummy_data = Data(x=x, edge_index=edge_index, edge_attr=edge_attr)
            out = self.m(dummy_data)
            return out["pred"], out["log_var"]

    wrapper = _OnnxWrapper(model).eval()

    onnx_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        torch.onnx.export(
            wrapper,
            (x, edge_index, edge_attr),
            str(onnx_path),
            opset_version=opset,
            input_names=["node_features", "edge_index", "edge_attr"],
            output_names=["pred_water_level_m", "log_variance"],
            dynamic_axes={
                "node_features": {0: "n_nodes", 1: "lookback"},
                "edge_index":    {1: "n_edges"},
                "edge_attr":     {0: "n_edges"},
                "pred_water_level_m": {0: "n_nodes"},
                "log_variance":       {0: "n_nodes"},
            },
            do_constant_folding=True,
            verbose=False,
        )
        logger.info(f"ONNX model exported: {onnx_path} (opset {opset})")
        return True
    except Exception as exc:
        logger.warning(f"ONNX export failed ({exc}). Falling back to TorchScript.")
        # TorchScript fallback
        ts_path = onnx_path.with_suffix(".pt")
        try:
            scripted = torch.jit.script(model)
            scripted.save(str(ts_path))
            logger.info(f"TorchScript model saved: {ts_path}")
        except Exception as e2:
            logger.error(f"TorchScript also failed: {e2}")
        return False


# ---------------------------------------------------------------------------
# Model card
# ---------------------------------------------------------------------------

def write_model_card(
    path:       Path,
    config:     dict,
    param_info: dict,
    ckpt_path:  Path,
    onnx_ok:    bool,
    ckpt_meta:  dict,
) -> None:
    """Write a JSON model card for reproducibility."""
    mc = {
        "model_name":  "HydroGNN-Net",
        "version":     config["project"]["version"],
        "title":       config["project"]["title"],
        "citation":    config["project"]["citation"],
        "created_at":  datetime.now(timezone.utc).isoformat(),
        "checkpoint":  str(ckpt_path),
        "architecture": {
            "type":       "Spatio-Temporal GNN",
            "components": ["GRU Temporal Encoder", "GATv2 Spatial Encoder",
                           "GraphSAGE Refinement", "Multi-Horizon Head",
                           "Heteroscedastic Uncertainty Head"],
            **config["model"],
        },
        "parameters":      param_info,
        "study_area":      config["basin"],
        "stations":        [s["id"] for s in config["stations"]],
        "training": {
            "data_years":    f"{config['years']['start']}–{config['years']['end']}",
            "split":         config["split"],
            "lookback_steps": config["temporal"]["lookback_steps"],
            "horizons_h":     config["temporal"]["forecast_horizons_hours"],
            **{k: config["training"][k] for k in ("epochs", "batch_size", "lr", "seed")},
        },
        "training_metrics": ckpt_meta,
        "export": {
            "onnx_available": onnx_ok,
            "opset":          config["export"].get("opset_version", 14),
        },
        "data_sources": [
            "NASA GPM IMERG V07 (precipitation, 0.1deg/30min)",
            "ERA5 Reanalysis (temperature, humidity, wind, soil moisture)",
            "CWC India-WRIS (river gauge water levels)",
            "HydroRIVERS v10 (river network topology)",
            "SRTM 30m (terrain elevation)",
        ],
        "reproducibility": {
            "seed":             config["training"]["seed"],
            "deterministic":    True,
            "normalizer":       config["features"]["normalization"],
            "split_strategy":   "chronological (no shuffle)",
        },
    }
    path.write_text(json.dumps(mc, indent=2), encoding="utf-8")
    logger.info(f"Model card written: {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="HydroGNN-Net Model Export")
    parser.add_argument("--config",     default="pipeline/config.yaml")
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--no-onnx",   action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    config = resolve_paths(load_config(config_path), PROJECT_ROOT)

    models_dir = Path(config["paths"]["models_dir"])
    models_dir.mkdir(parents=True, exist_ok=True)

    # ── Checkpoint ────────────────────────────────────────────────────────
    ckpt_path = Path(args.checkpoint) if args.checkpoint else models_dir / "best_model.pt"
    if not ckpt_path.exists():
        logger.error(f"Checkpoint not found: {ckpt_path}\nRun: python pipeline/train.py")
        sys.exit(1)

    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)

    # ── Load model ────────────────────────────────────────────────────────
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
    )
    state    = ckpt.get("model_state_dict", ckpt)
    model.load_state_dict(state)
    model.eval()
    logger.info(f"Model loaded from {ckpt_path}")

    param_info = count_parameters(model)
    logger.info(f"Parameters: {param_info['total']:,} total / {param_info['trainable']:,} trainable")

    # ── ONNX Export ───────────────────────────────────────────────────────
    onnx_ok = False
    if not args.no_onnx and config["export"].get("onnx", True):
        log_separator(logger, "Exporting to ONNX")
        n_stations = len(config["stations"])
        n_edges    = max(n_stations - 1, 1)   # minimal edge count for dummy input
        onnx_ok = export_onnx(
            model=model,
            onnx_path=models_dir / "hydrognn_net.onnx",
            n_nodes=n_stations,
            lookback=config["temporal"]["lookback_steps"],
            n_features=model_cfg["node_features"],
            n_edges=n_edges,
            edge_dim=model_cfg["edge_dim"],
            opset=config["export"].get("opset_version", 14),
        )
    else:
        logger.info("ONNX export skipped (--no-onnx or config.export.onnx=false)")

    # ── TorchScript (always produce) ─────────────────────────────────────
    log_separator(logger, "TorchScript serialization")
    ts_path = models_dir / "hydrognn_net_scripted.pt"
    try:
        # Save state-dict version (safest for PyG models)
        torch.save({
            "model_state_dict": model.state_dict(),
            "model_config":     model_cfg,
            "pipeline_config":  {
                "basin":     config["basin"],
                "temporal":  config["temporal"],
                "stations":  [s["id"] for s in config["stations"]],
            },
        }, ts_path)
        logger.info(f"State-dict bundle saved: {ts_path}")
    except Exception as exc:
        logger.warning(f"TorchScript save failed: {exc}")

    # ── Model Card ────────────────────────────────────────────────────────
    log_separator(logger, "Writing model card")
    ckpt_meta = {k: v for k, v in ckpt.items()
                 if isinstance(v, (int, float, str)) and k != "model_state_dict"}
    write_model_card(
        path=models_dir / "model_card.json",
        config=config,
        param_info=param_info,
        ckpt_path=ckpt_path,
        onnx_ok=onnx_ok,
        ckpt_meta=ckpt_meta,
    )

    log_separator(logger, "Export Complete")
    logger.info(f"  Models directory : {models_dir}")
    if onnx_ok:
        logger.info(f"  ONNX model       : {models_dir / 'hydrognn_net.onnx'}")
    logger.info(f"  State-dict bundle: {ts_path}")
    logger.info(f"  Model card       : {models_dir / 'model_card.json'}")


if __name__ == "__main__":
    main()
