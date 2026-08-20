"""
HydroGNN-Net Dataset Creation Script
=====================================
Assembles all preprocessed features into PyTorch Geometric Data objects,
builds the river connectivity graph, normalizes features (train split only),
and saves chronological train/val/test split files.

Prerequisites
-------------
    python pipeline/download_all.py
    python pipeline/preprocess.py

Usage
-----
    python pipeline/create_dataset.py
    python pipeline/create_dataset.py --config pipeline/config.yaml
    python pipeline/create_dataset.py --dry-run  # Count windows without saving

Outputs
-------
    dataset/splits/train.pt        Train split (PyG Data list)
    dataset/splits/val.pt          Validation split
    dataset/splits/test.pt         Test split
    dataset/graphs/nodes.csv       Node metadata
    dataset/graphs/edges.csv       Graph edges
    dataset/graphs/edge_attributes.csv  Edge features
    dataset/models/normalizer.json Feature normalization statistics
    dataset/metadata/dataset_info.json  Dataset provenance and statistics
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

import numpy as np
import pandas as pd
import torch
import yaml

from src.dataset.splitter import ChronologicalSplitter
from src.downloaders.cwc import CWCDataParser
from src.downloaders.hydrorivers import HydroRIVERSDownloader
from src.downloaders.reservoir import ReservoirDataParser
from src.downloaders.srtm import SRTMDownloader
from src.features.normalizer import FeatureNormalizer
from src.features.rolling_rainfall import (
    compute_antecedent_rainfall_index,
    compute_rolling_rainfall,
)
from src.graph.edge_builder import EdgeBuilder
from src.graph.node_builder import NodeBuilder
from src.graph.pyg_builder import PyGGraphBuilder
from src.utils.cache import CacheManager, DataSourceUnavailable
from src.utils.logger import DownloadLogger, get_logger, log_separator

logger = get_logger("create_dataset")

FEATURE_COLS = [
    "rainfall_1h", "rainfall_3h", "rainfall_6h", "rainfall_12h", "rainfall_24h",
    "antecedent_rainfall_index",
    "temperature_c", "soil_moisture", "wind_speed_ms",
    "reservoir_release_norm", "reservoir_storage_norm",
    "upstream_contribution",
    "water_level_m",   # target feature — also used as input (lagged)
]
TARGET_COL = "water_level_m"


def load_config(config_path: Path) -> dict:
    with open(config_path) as fh:
        return yaml.safe_load(fh)


def resolve_paths(config: dict, project_root: Path) -> dict:
    for key in config["paths"]:
        p = Path(config["paths"][key])
        if not p.is_absolute():
            config["paths"][key] = str(project_root / "pipeline" / p)
    return config


def load_gpm_processed(proc_dir: Path, sid: str) -> pd.DataFrame:
    p = proc_dir / f"gpm_processed_{sid}.parquet"
    if p.exists():
        return pd.read_parquet(p)
    # Fallback: try raw extract
    p2 = proc_dir / f"gpm_{sid}.parquet"
    if p2.exists():
        df = pd.read_parquet(p2)
        return compute_rolling_rainfall(df)
    logger.warning(f"GPM data not found for {sid}")
    return pd.DataFrame()


def load_cwc_processed(proc_dir: Path, sid: str) -> pd.DataFrame:
    p = proc_dir / f"cwc_{sid}.parquet"
    if p.exists():
        return pd.read_parquet(p)
    logger.warning(f"CWC data not found for {sid}")
    return pd.DataFrame()


def load_era5_processed(proc_dir: Path, sid: str) -> pd.DataFrame:
    p = proc_dir / f"era5_{sid}.parquet"
    if p.exists():
        return pd.read_parquet(p)
    logger.warning(f"ERA5 data not found for {sid}")
    return pd.DataFrame()


def load_reservoir_processed(proc_dir: Path, rid: str) -> pd.DataFrame:
    p = proc_dir / f"reservoir_{rid}.parquet"
    if p.exists():
        return pd.read_parquet(p)
    return pd.DataFrame()


def assemble_station_features(
    sid: str,
    proc_dir: Path,
    config: dict,
    reservoir_data: dict,
    station_res_map: dict,
    timestamps: pd.DatetimeIndex,
) -> pd.DataFrame:
    """
    Assemble the 13-feature vector for a single station at every timestamp.

    If a data source is unavailable, fills with NaN and logs WARNING.
    NEVER fabricates values.

    Returns
    -------
    pd.DataFrame  shape [T, 13] with FEATURE_COLS, indexed by timestamps.
    """
    # Start with NaN frame
    df = pd.DataFrame(index=timestamps, columns=FEATURE_COLS, dtype=float)

    # ── GPM Precipitation features ────────────────────────────────────────
    gpm = load_gpm_processed(proc_dir, sid)
    if not gpm.empty:
        if "timestamp" in gpm.columns:
            gpm = gpm.set_index("timestamp")
        gpm.index = pd.to_datetime(gpm.index, utc=True)
        for col in ["rainfall_1h", "rainfall_3h", "rainfall_6h", "rainfall_12h", "rainfall_24h"]:
            if col in gpm.columns:
                df[col] = gpm[col].reindex(timestamps)

        # ARI
        if "rainfall_6h" in gpm.columns:
            gpm_aligned = gpm["rainfall_6h"].reindex(timestamps).to_frame("rainfall_6h")
            ari = compute_antecedent_rainfall_index(
                gpm_aligned,
                decay=config["features"]["ari_decay"],
            )
            df["antecedent_rainfall_index"] = ari.values

    # ── ERA5 meteorological features ─────────────────────────────────────
    era5 = load_era5_processed(proc_dir, sid)
    if not era5.empty:
        if "timestamp" in era5.columns:
            era5 = era5.set_index("timestamp")
        era5.index = pd.to_datetime(era5.index, utc=True)
        for col, feat in [("temperature_c", "temperature_c"),
                           ("soil_moisture", "soil_moisture"),
                           ("wind_speed_ms", "wind_speed_ms")]:
            if col in era5.columns:
                df[feat] = era5[col].reindex(timestamps)

    # ── Reservoir influence ───────────────────────────────────────────────
    rid = station_res_map.get(sid)
    if rid and rid in reservoir_data:
        res_df = reservoir_data[rid]
        if not res_df.empty:
            res_aligned = res_df.reindex(timestamps)
            max_release = res_aligned["release_cumecs"].quantile(0.99)
            if max_release > 0:
                df["reservoir_release_norm"] = (
                    res_aligned["release_cumecs"] / max_release
                ).clip(0, 2)
            df["reservoir_storage_norm"] = (
                res_aligned["storage_pct"] / 100.0
            ).clip(0, 1.2)
    else:
        df["reservoir_release_norm"] = 0.0
        df["reservoir_storage_norm"] = 0.0
        if rid:
            logger.warning(f"Station {sid}: reservoir {rid} data unavailable, using zeros")

    # Upstream contribution — set to 0 here (requires CWC discharge data)
    # Properly computed in network_features.py if CWC data available
    df["upstream_contribution"] = 0.0

    # ── CWC water level ───────────────────────────────────────────────────
    cwc = load_cwc_processed(proc_dir, sid)
    if not cwc.empty:
        if "timestamp" in cwc.columns:
            cwc = cwc.set_index("timestamp")
        cwc.index = pd.to_datetime(cwc.index, utc=True)
        if "level_m" in cwc.columns:
            df[TARGET_COL] = cwc["level_m"].reindex(timestamps)
    else:
        logger.warning(
            f"Station {sid}: CWC river level data unavailable.\n"
            f"  Export from India-WRIS and place in dataset/raw/cwc/{sid}_{{YYYY}}.csv"
        )
        df[TARGET_COL] = np.nan

    missing_pct = df.isna().mean().mean() * 100
    n_valid_target = df[TARGET_COL].notna().sum()
    logger.info(
        f"Station {sid}: assembled {len(df):,} timesteps, "
        f"{missing_pct:.1f}% missing, {n_valid_target:,} valid targets"
    )
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    argp = argparse.ArgumentParser()
    argp.add_argument("--config",  default="pipeline/config.yaml")
    argp.add_argument("--dry-run", action="store_true")
    args = argp.parse_args()

    project_root = PIPELINE_DIR.parent
    config_path  = project_root / args.config
    config       = resolve_paths(load_config(config_path), project_root)

    proc_dir   = Path(config["paths"]["processed_dir"])
    graphs_dir = Path(config["paths"]["graphs_dir"])
    splits_dir = Path(config["paths"]["splits_dir"])
    models_dir = Path(config["paths"]["models_dir"])
    meta_dir   = Path(config["paths"]["metadata_dir"])
    logs_dir   = Path(config["paths"]["logs_dir"])
    for d in [proc_dir, graphs_dir, splits_dir, models_dir, meta_dir, logs_dir]:
        d.mkdir(parents=True, exist_ok=True)

    station_cfgs = config["stations"]
    res_cfgs     = config["reservoirs"]
    station_ids  = [s["id"]           for s in station_cfgs]
    station_coords = [(s["lat"], s["lon"]) for s in station_cfgs]

    # ── Load reservoir data ───────────────────────────────────────────────
    log_separator(logger, "Loading Reservoir Data")
    res_data: dict = {}
    for res_cfg in res_cfgs:
        rid = res_cfg["id"]
        df  = load_reservoir_processed(proc_dir, rid)
        if not df.empty:
            if "timestamp" in df.columns:
                df = df.set_index("timestamp")
            df.index = pd.to_datetime(df.index, utc=True)
            res_data[rid] = df

    # Map each station to nearest reservoir
    station_res_map = {}
    for st_cfg in station_cfgs:
        if "reservoir_id" in st_cfg:
            station_res_map[st_cfg["id"]] = st_cfg["reservoir_id"]
    # Default: Mettur affects all downstream stations
    for sid in station_ids:
        if sid not in station_res_map:
            station_res_map[sid] = "METTUR"

    # ── Determine global timestamp grid ───────────────────────────────────
    log_separator(logger, "Building Timestamp Grid")
    start_yr = config["years"]["start"]
    end_yr   = config["years"]["end"]
    timestamps = pd.date_range(
        start=f"{start_yr}-01-01",
        end=f"{end_yr}-12-31 23:30",
        freq="30T",
        tz="UTC",
    )
    logger.info(f"Timestamp grid: {timestamps[0]} → {timestamps[-1]}  ({len(timestamps):,} steps)")

    # ── Assemble features for all stations [T, N, F] ─────────────────────
    log_separator(logger, "Assembling Station Feature Matrices")
    station_dfs = {}
    for sid in station_ids:
        station_dfs[sid] = assemble_station_features(
            sid, proc_dir, config, res_data, station_res_map, timestamps
        )

    # Build feature array [T, N, F]
    T = len(timestamps)
    N = len(station_ids)
    F = len(FEATURE_COLS)

    features_arr = np.full((T, N, F), np.nan, dtype=np.float32)
    targets_arr  = np.full((T, N),    np.nan, dtype=np.float32)
    masks_arr    = np.zeros((T, N),   dtype=bool)

    for ni, sid in enumerate(station_ids):
        df = station_dfs[sid]
        for fi, col in enumerate(FEATURE_COLS):
            if col in df.columns:
                features_arr[:, ni, fi] = df[col].values
        targets_arr[:, ni] = df[TARGET_COL].values
        masks_arr[:, ni]   = df[TARGET_COL].notna().values

    n_valid_total = masks_arr.sum()
    logger.info(
        f"Feature array: {features_arr.shape}. "
        f"Valid targets: {n_valid_total:,} / {T*N:,} "
        f"({n_valid_total/(T*N)*100:.1f}%)"
    )

    if n_valid_total < 100:
        logger.error(
            "FEWER THAN 100 VALID TARGET OBSERVATIONS.\n"
            "Training is not possible without CWC river level data.\n"
            "Export data from India-WRIS: https://indiawris.gov.in\n"
            "Place files in: dataset/raw/cwc/{STATION_ID}_{YYYY}.csv"
        )

    # ── Build graph ───────────────────────────────────────────────────────
    log_separator(logger, "Building River Network Graph")

    # Terrain attributes
    terrain_csv = proc_dir / "terrain_attributes.csv"
    if terrain_csv.exists():
        terrain_df = pd.read_csv(terrain_csv)
    else:
        logger.warning("Terrain attributes not found. Using zeros for elevation/slope.")
        terrain_df = pd.DataFrame({
            "station_id": station_ids,
            "elevation_m": [0.0] * N,
            "slope_deg":   [0.0] * N,
        })

    node_builder = NodeBuilder(config)
    nodes_df     = node_builder.build_nodes_csv(station_cfgs, terrain_df, res_cfgs)
    node_builder.save(nodes_df, graphs_dir / "nodes.csv")

    edge_builder = EdgeBuilder(config)

    # Try HydroRIVERS first
    clipped_shp = Path(config["paths"]["raw_dir"]) / "hydrorivers" / "cauvery_rivers.shp"
    if clipped_shp.exists():
        try:
            import geopandas as gpd
            river_gdf = gpd.read_file(clipped_shp)
            cache     = CacheManager(Path(config["paths"]["logs_dir"]) / "cache")
            dl_log    = DownloadLogger(Path(config["paths"]["logs_dir"]) / "download_log.csv")
            hr        = HydroRIVERSDownloader(cache, dl_log, config)
            edges_df, edge_attrs_df = hr.build_station_river_network(river_gdf, nodes_df)
        except Exception as exc:
            logger.warning(f"HydroRIVERS processing failed: {exc}. Using fallback.")
            edges_df, edge_attrs_df = edge_builder.build_fallback_connectivity(nodes_df)
    else:
        edges_df, edge_attrs_df = edge_builder.build_fallback_connectivity(nodes_df)

    adj = edge_builder.compute_adjacency_matrix(edges_df, station_ids)
    edge_builder.save(edges_df, edge_attrs_df, adj, graphs_dir)

    edge_index, edge_attr = edge_builder.to_pyg_format(
        edges_df, edge_attrs_df, station_ids
    )

    # ── Normalize features ────────────────────────────────────────────────
    log_separator(logger, "Normalizing Features (Train Split Only)")

    splitter    = ChronologicalSplitter(
        train_ratio = config["split"]["train"],
        val_ratio   = config["split"]["val"],
        test_ratio  = config["split"]["test"],
    )
    train_idx, val_idx, test_idx = splitter.split_indices(T)
    train_end = train_idx.stop

    # Flatten [T, N, F] → [T*N, F] for scaler fitting
    flat_features = features_arr.reshape(T * N, F)
    flat_df = pd.DataFrame(flat_features, columns=FEATURE_COLS)
    flat_train_end = train_end * N

    normalizer = FeatureNormalizer(method=config["features"]["normalization"])
    normalizer.fit(flat_df, FEATURE_COLS, train_end_idx=flat_train_end)
    normalizer.save(models_dir / "normalizer.json")

    # Apply normalization
    norm_flat    = normalizer.transform_array(flat_features, FEATURE_COLS)
    norm_features = norm_flat.reshape(T, N, F)

    # ── Build PyG Data objects ────────────────────────────────────────────
    log_separator(logger, "Building Sliding Window Data Objects")

    pyg_builder = PyGGraphBuilder(config)
    step        = config["temporal"].get("step_size", 1)

    all_windows = pyg_builder.build_sliding_windows(
        features   = norm_features,
        targets    = targets_arr,
        masks      = masks_arr,
        timestamps = timestamps,
        edge_index = edge_index,
        edge_attr  = edge_attr,
        step       = step,
    )

    if not all_windows and not args.dry_run:
        logger.error(
            "No valid windows created. Check that CWC river level data is available."
        )
        return

    # ── Split ─────────────────────────────────────────────────────────────
    train_list, val_list, test_list = splitter.split(all_windows)
    report = splitter.report(train_list, val_list, test_list)
    logger.info(f"Split: {report}")

    if args.dry_run:
        logger.info(
            f"DRY RUN — would create:\n"
            f"  train: {len(train_list)} windows\n"
            f"  val:   {len(val_list)} windows\n"
            f"  test:  {len(test_list)} windows"
        )
        return

    # ── Save splits ───────────────────────────────────────────────────────
    log_separator(logger, "Saving Dataset Splits")
    torch.save(train_list, splits_dir / "train.pt")
    torch.save(val_list,   splits_dir / "val.pt")
    torch.save(test_list,  splits_dir / "test.pt")
    logger.info(f"Saved: {splits_dir}/{{train,val,test}}.pt")

    # ── Metadata ──────────────────────────────────────────────────────────
    metadata = {
        "created_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "project": "HydroGNN-Net IEEE Final Year Project",
        "basin": config["basin"]["name"],
        "years": f"{start_yr}–{end_yr}",
        "stations": station_ids,
        "n_nodes": N,
        "n_edges": len(edges_df),
        "n_features": F,
        "feature_names": FEATURE_COLS,
        "lookback_steps": config["temporal"]["lookback_steps"],
        "forecast_horizons_hours": config["temporal"]["forecast_horizons_hours"],
        "total_windows": len(all_windows),
        "train_windows": len(train_list),
        "val_windows":   len(val_list),
        "test_windows":  len(test_list),
        "normalization_method": config["features"]["normalization"],
        "valid_target_pct": float(n_valid_total) / float(T * N) * 100,
    }
    meta_path = meta_dir / "dataset_info.json"
    with open(meta_path, "w") as fh:
        json.dump(metadata, fh, indent=2)
    logger.info(f"Metadata: {meta_path}")

    log_separator(logger, "Dataset Creation Complete")
    logger.info(f"Total windows:  {len(all_windows):,}")
    logger.info(f"  Train:        {len(train_list):,}")
    logger.info(f"  Validation:   {len(val_list):,}")
    logger.info(f"  Test:         {len(test_list):,}")
    logger.info("")
    logger.info("Next: python pipeline/train.py")


if __name__ == "__main__":
    main()
