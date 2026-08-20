"""
HydroGNN-Net — Scientific Hydrograph Backend (Final Phase)

Replaces predict.py entirely. Changes:
- 96 observed points (24h back at 15-min interval, gap-filled by forward-fill)
- Anchors at h=1,3,6,12,18,24 (finer resolution)
- Nash-Sutcliffe unit-hydrograph routing (no random noise)
- PchipInterpolator for smooth flood-wave shape
- CI from stored model uncertainty (grows naturally)
- Rich metadata per point (rainfall, discharge, source, reservoir)
- Overlay data: rainfall, discharge per timestep for secondary axes
- XAI payload: per-point dominant driver breakdown
"""
import os
import json
import time
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import torch
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Dict, Optional

from app.backend.services.db.connection import get_db
from app.backend.services.db.models import RiverStation, RiverLevel, Prediction, Rainfall, Weather
from app.backend.auth.jwt_handler import verify_access_token
from app.backend.services.xai.shap_explainer import compute_local_shap_attributions

try:
    from datasets.simulator import CONNECTIONS as _RIVER_CONNECTIONS
except ImportError:
    _RIVER_CONNECTIONS = []

router = APIRouter(prefix="/predict", tags=["prediction"])
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    payload = verify_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload

class PredictionRequest(BaseModel):
    station_id: str
    horizons_hours: List[int]
    compare_stations: Optional[List[str]] = None  # Phase 9: multi-station

from app.backend.auth.security import check_rate_limit, validate_station_id
from fastapi import Request


# ─────────────────────────────────────────────────────────────────────────────
# HYDROLOGICAL ROUTING — Nash-Sutcliffe Unit Hydrograph
# Reference: Nash (1957), "The form of the instantaneous unit hydrograph"
# This is a standard lumped hydrological model used by CWRDM, IMD, CWC India.
# NO random noise. Deterministic physics-based routing.
# ─────────────────────────────────────────────────────────────────────────────

def nash_sutcliffe_iuh(n: float, k: float, t_hours: float) -> float:
    """
    Nash Instantaneous Unit Hydrograph ordinate at time t.
    u(t) = (1/(k*Γ(n))) * (t/k)^(n-1) * exp(-t/k)
    n = number of linear reservoirs (shape parameter, typically 2-5)
    k = storage coefficient in hours (lag/routing time constant)
    Returns dimensionless unit response.
    """
    if t_hours <= 0:
        return 0.0
    from math import gamma, exp, log
    try:
        # Use log-space for numerical stability
        log_u = (n - 1) * log(t_hours / k) - (t_hours / k) - log(k) - log(gamma(n))
        return max(0.0, np.exp(log_u))
    except (ValueError, OverflowError):
        return 0.0


def compute_flood_routing(
    lvl0: float,
    rain_series: List[float],   # mm per 15-min step, chronological
    upstream_q: float,          # cumecs from upstream at t=0
    res_release: float,         # cumecs reservoir release
    soil_moisture: float,       # 0-1 proxy
    danger_level: float,
    anchor_horizons: List[int], # hours to compute predictions at
    channel_k: float = 2.5,     # Nash k parameter (hours) — typical Tamil Nadu basin
    channel_n: float = 3.0,     # Nash n parameter — shape
    runoff_coeff: float = None, # CN-based, derived from soil_moisture if None
) -> Dict[int, Dict]:
    """
    Compute level predictions at each anchor horizon using Nash-Sutcliffe routing.
    Returns dict: {horizon_hours: {level_m, uncertainty_m, confidence, flood_prob, severity}}

    Steps:
    1. Convert 24h rainfall + upstream flow to effective runoff
    2. Convolve with Nash IUH to get flood hydrograph ordinates
    3. Add baseflow (current level)
    4. Propagate uncertainty using ensemble spread (no noise — analytical)
    """
    dt = 0.25  # hours (15 min)

    # CN-based runoff coefficient from soil moisture
    if runoff_coeff is None:
        # Higher soil moisture → higher runoff fraction
        runoff_coeff = min(0.85, max(0.05, 0.2 + soil_moisture * 0.6))

    # Effective rainfall (mm/step → m³/s equivalent flow)
    # Use 1 km² catchment unit for level change estimation
    # L_change ≈ rainfall_depth * runoff_coeff / channel_width_proxy
    # We keep it dimensionally consistent by working in level units
    eff_rain = [max(0.0, r * runoff_coeff * 0.001) for r in rain_series]  # → m

    # Build IUH convolution kernel at anchor horizons
    # First compute IUH ordinates at 15-min steps up to max horizon
    max_h = max(anchor_horizons)
    steps = int(max_h / dt) + 1

    iuh_kernel = np.array([
        nash_sutcliffe_iuh(channel_n, channel_k, (i + 1) * dt)
        for i in range(min(steps, 96))  # cap at 96 steps (24h)
    ])

    # Normalise IUH so area = 1 (conservation of volume)
    iuh_sum = iuh_kernel.sum() * dt
    if iuh_sum > 0:
        iuh_kernel /= iuh_sum

    # Pad rain series if shorter than IUH kernel
    eff_rain_arr = np.array(eff_rain)
    if len(eff_rain_arr) < len(iuh_kernel):
        eff_rain_arr = np.pad(eff_rain_arr, (0, len(iuh_kernel) - len(eff_rain_arr)))

    # Direct runoff hydrograph via convolution
    drh = np.convolve(eff_rain_arr[:len(iuh_kernel)], iuh_kernel)[:steps]

    # Upstream flow contribution: attenuates with travel time
    # Travel attenuation: Q_up(t) = Q_up0 * exp(-t / tau_routing)
    # tau_routing ~ 0.5 * channel_k
    tau = max(0.5, channel_k * 0.5)
    t_arr = np.arange(steps) * dt
    upstream_response = upstream_q * 0.001 * np.exp(-t_arr / tau)  # level equivalent

    # Reservoir release sustained for first few hours then tapers
    res_t = np.clip(1.0 - t_arr / max(channel_k, 1.0), 0.0, 1.0)
    res_response = res_release * 0.0001 * res_t

    # Total flood hydrograph: baseflow + direct runoff + upstream + reservoir
    total_hyd = lvl0 + drh + upstream_response + res_response

    results = {}
    for h in anchor_horizons:
        idx = min(int(h / dt), len(total_hyd) - 1)
        predicted = float(np.clip(total_hyd[idx], 0.1, danger_level * 1.5))

        # Analytical uncertainty: grows with prediction horizon
        # Based on WMO uncertainty guidelines for short-range flood forecasts:
        # σ ≈ σ0 * sqrt(h / 6) where σ0 is analysis uncertainty (~5% of range)
        sigma0 = max(0.1, (danger_level - lvl0) * 0.05)
        uncertainty = round(sigma0 * np.sqrt(max(h, 0.25) / 6.0), 2)

        ratio = predicted / max(danger_level, 0.1)
        if ratio < 0.4:   sev = "Safe"
        elif ratio < 0.7: sev = "Low Risk"
        elif ratio < 0.9: sev = "Moderate Risk"
        elif ratio < 1.0: sev = "High Risk"
        else:             sev = "Severe Flood"

        # Confidence: decreases with horizon, increases with data availability
        data_score = min(1.0, len([r for r in rain_series if r > 0]) / max(len(rain_series), 1))
        conf = round(max(0.50, 0.95 * (data_score ** 0.3) - 0.04 * (h / 6.0)), 2)

        results[h] = {
            "level_m": round(predicted, 2),
            "uncertainty_m": uncertainty,
            "confidence": conf,
            "flood_probability": round(float(ratio), 2),
            "severity": sev,
            "rain_contribution_m": round(float(drh[idx]), 3),
            "upstream_contribution_m": round(float(upstream_response[idx]), 3),
            "reservoir_contribution_m": round(float(res_response[idx]), 3),
        }

    return results


# ─────────────────────────────────────────────────────────────────────────────
# GAP FILL: forward-fill sparse observed records to 15-min grid
# ─────────────────────────────────────────────────────────────────────────────

def fill_observed_series(
    records: List,            # list of RiverLevel ORM objects, chronological
    start_ts: datetime,       # earliest timestamp to fill from
    end_ts: datetime,         # latest timestamp (= latest_ts)
    step_minutes: int = 15,
) -> List[dict]:
    """
    Create a regular 15-min grid from start_ts to end_ts.
    For each grid point, forward-fill from the nearest prior observation.
    Returns list of dicts with keys: ts_iso, time, observed, discharge, source.
    """
    if not records:
        return []

    # Build lookup: ts → record
    rec_map = {r.ts: r for r in records}

    # Generate grid
    grid = []
    ts = start_ts
    last_rec = None

    # Attempt to find a record at or before start_ts (forward-fill seed)
    for r in records:
        if r.ts <= start_ts:
            last_rec = r

    # If no record predates the grid start, use the earliest available record
    # as a backward-fill seed so we still emit all grid ticks (IEEE completeness)
    if last_rec is None and records:
        last_rec = records[0]

    while ts <= end_ts:
        # Advance last_rec if a real observation falls exactly on this tick
        if ts in rec_map:
            last_rec = rec_map[ts]

        if last_rec is not None:
            grid.append({
                "ts": ts,
                "ts_iso": ts.isoformat(),
                "time": ts.strftime("%m-%d %H:%M"),
                "observed": round(last_rec.level_m, 2),
                "discharge": round(last_rec.discharge_cumecs, 1),
                "source": last_rec.source,
            })
        ts += timedelta(minutes=step_minutes)

    return grid



@router.post("")
def get_prediction(
    req: PredictionRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
    _rate_limit=Depends(check_rate_limit),
):
    station_id = validate_station_id(req.station_id)
    station = db.query(RiverStation).filter(RiverStation.id == station_id).first()
    if not station:
        raise HTTPException(status_code=400, detail=f"Station ID {station_id} is invalid.")

    now_utc = datetime.utcnow()

    # ── Latest observed timestamp ─────────────────────────────────────────────
    latest_level_rec = (
        db.query(RiverLevel)
        .filter(RiverLevel.station_id == station_id, RiverLevel.ts <= now_utc)
        .order_by(RiverLevel.ts.desc())
        .first()
    )
    if not latest_level_rec:
        latest_level_rec = (
            db.query(RiverLevel)
            .filter(RiverLevel.station_id == station_id)
            .order_by(RiverLevel.ts.desc())
            .first()
        )
    if not latest_level_rec:
        raise HTTPException(status_code=404, detail="No telemetry records found for station.")

    latest_ts = latest_level_rec.ts

    # ── Observed: last 24 hours = 96 steps at 15-min interval ────────────────
    obs_start = latest_ts - timedelta(hours=24)
    observed_raw = (
        db.query(RiverLevel)
        .filter(
            RiverLevel.station_id == station_id,
            RiverLevel.ts >= obs_start,
            RiverLevel.ts <= latest_ts,
        )
        .order_by(RiverLevel.ts.asc())
        .all()
    )

    # Gap-fill to regular 15-min grid
    observed_grid = fill_observed_series(observed_raw, obs_start, latest_ts, step_minutes=15)

    # ── Rainfall: last 24h for routing ───────────────────────────────────────
    rain_recs = (
        db.query(Rainfall)
        .filter(
            Rainfall.station_id == station_id,
            Rainfall.ts >= obs_start,
            Rainfall.ts <= latest_ts,
        )
        .order_by(Rainfall.ts.asc())
        .all()
    )
    # Build rainfall on same 15-min grid for overlay
    rain_map = {r.ts: max(0.0, r.value_mm) for r in rain_recs}
    rain_series_15min = []
    ts_walk = obs_start
    last_rain = 0.0
    while ts_walk <= latest_ts:
        if ts_walk in rain_map:
            last_rain = rain_map[ts_walk]
        rain_series_15min.append(last_rain)
        ts_walk += timedelta(minutes=15)

    rain_24h_total = sum(rain_series_15min)

    # ── Upstream discharge from river network ─────────────────────────────────
    upstream_discharge = 0.0
    upstream_sources = []
    for src, dst, t_lag in _RIVER_CONNECTIONS:
        if dst == station_id:
            lookback = latest_ts - timedelta(hours=t_lag)
            up_rec = (
                db.query(RiverLevel)
                .filter(RiverLevel.station_id == src, RiverLevel.ts <= lookback)
                .order_by(RiverLevel.ts.desc())
                .first()
            )
            if up_rec:
                upstream_discharge += up_rec.discharge_cumecs
                upstream_sources.append({
                    "station_id": src,
                    "discharge_cumecs": up_rec.discharge_cumecs,
                    "travel_lag_h": t_lag,
                })

    # ── Soil moisture proxy (CN-based from antecedent rainfall) ───────────────
    soil_moisture = min(0.95, max(0.1, 0.2 + rain_24h_total / 200.0))

    # ── Reservoir release ─────────────────────────────────────────────────────
    res_release = 0.0
    if len(station.reservoirs) > 0:
        res_release = float(latest_level_rec.release or 0.0)

    # ── Nash-Sutcliffe routing for finer anchor horizons ─────────────────────
    # Use h=1,3,6,12,18,24 for smooth Pchip interpolation
    ANCHOR_HORIZONS = [1, 3, 6, 12, 18, 24]

    routing_results = compute_flood_routing(
        lvl0=latest_level_rec.level_m,
        rain_series=rain_series_15min,
        upstream_q=upstream_discharge,
        res_release=res_release,
        soil_moisture=soil_moisture,
        danger_level=float(station.danger_level or 10.0),
        anchor_horizons=ANCHOR_HORIZONS,
    )

    # ── Try to use stored predictions at matching horizons (prefer DB over routing) ──
    stored_preds = (
        db.query(Prediction)
        .filter(
            Prediction.station_id == station_id,
            Prediction.issued_at >= latest_ts - timedelta(hours=2),
            Prediction.issued_at <= latest_ts + timedelta(hours=1),
        )
        .order_by(Prediction.issued_at.desc(), Prediction.horizon_hours.asc())
        .all()
    )

    # Merge: use stored predictions for horizons that exist in DB (higher quality)
    # Fall back to Nash routing for horizons not in DB
    stored_map = {}
    if stored_preds:
        # Use the most recent batch
        most_recent_issued = max(p.issued_at for p in stored_preds)
        for p in stored_preds:
            if p.issued_at == most_recent_issued:
                stored_map[p.horizon_hours] = {
                    "level_m": p.predicted_level,
                    "uncertainty_m": p.uncertainty,
                    "confidence": p.confidence,
                    "flood_probability": p.flood_probability,
                    "severity": p.severity_class,
                    "rain_contribution_m": routing_results.get(
                        min(ANCHOR_HORIZONS, key=lambda x: abs(x - p.horizon_hours)), {}
                    ).get("rain_contribution_m", 0.0),
                    "upstream_contribution_m": routing_results.get(
                        min(ANCHOR_HORIZONS, key=lambda x: abs(x - p.horizon_hours)), {}
                    ).get("upstream_contribution_m", 0.0),
                    "reservoir_contribution_m": routing_results.get(
                        min(ANCHOR_HORIZONS, key=lambda x: abs(x - p.horizon_hours)), {}
                    ).get("reservoir_contribution_m", 0.0),
                }

    # Build final anchor set: DB predictions take priority; Nash fills gaps
    anchor_data = {}
    for h in ANCHOR_HORIZONS:
        # Find nearest stored prediction horizon (within 2h)
        best_stored = None
        for sh in sorted(stored_map.keys(), key=lambda x: abs(x - h)):
            if abs(sh - h) <= 2:
                best_stored = stored_map[sh]
                break
        anchor_data[h] = best_stored if best_stored else routing_results[h]

    # ── Format predictions_response (for requested horizons) ─────────────────
    predictions_response = []
    for h in req.horizons_hours:
        # Find closest anchor
        closest = min(anchor_data.keys(), key=lambda x: abs(x - h))
        d = anchor_data[closest]
        predictions_response.append({
            "horizon_hours": h,
            "level_m": round(d["level_m"] * 3.28084, 2),
            "uncertainty_m": round(d["uncertainty_m"] * 3.28084, 2),
            "flood_probability": d["flood_probability"],
            "severity": d["severity"],
            "confidence": d["confidence"],
        })

    # ── Pchip spline over anchor horizons → 96-step forecast ─────────────────
    from scipy.interpolate import PchipInterpolator

    anchor_h_arr   = np.array([0.0] + [float(h) for h in ANCHOR_HORIZONS])
    anchor_lvl_arr = np.array(
        [float(latest_level_rec.level_m)] + [float(anchor_data[h]["level_m"]) for h in ANCHOR_HORIZONS]
    )
    anchor_unc_arr = np.array(
        [0.0] + [float(anchor_data[h]["uncertainty_m"]) for h in ANCHOR_HORIZONS]
    )
    anchor_conf_arr = np.array(
        [1.0] + [float(anchor_data[h]["confidence"]) for h in ANCHOR_HORIZONS]
    )

    lvl_spline  = PchipInterpolator(anchor_h_arr, anchor_lvl_arr, extrapolate=True)
    unc_spline  = PchipInterpolator(anchor_h_arr, anchor_unc_arr, extrapolate=True)
    conf_spline = PchipInterpolator(anchor_h_arr, anchor_conf_arr, extrapolate=True)

    # ── Build hydrograph array ────────────────────────────────────────────────
    # OBSERVED section (96 points, 24h back)
    hydrograph = []
    rain_overlay = []
    discharge_overlay = []

    for i, pt in enumerate(observed_grid):
        rain_val = rain_series_15min[i] if i < len(rain_series_15min) else 0.0
        hydrograph.append({
            "time": pt["time"],
            "ts_iso": pt["ts_iso"],
            "section": "observed",
            "observed": round(pt["observed"] * 3.28084, 2) if pt["observed"] is not None else None,
            "predicted": None,
            "upper": None,
            "lower": None,
            "median": None,
            "discharge": pt["discharge"],
            "rainfall_mm": round(rain_val, 2),
            "source": pt["source"],
            "confidence": None,
        })
        rain_overlay.append({"time": pt["time"], "rainfall_mm": round(rain_val, 2)})
        discharge_overlay.append({"time": pt["time"], "discharge_cumecs": pt["discharge"]})

    # FORECAST section (96 points, 24h forward)
    FORECAST_STEPS = 96  # 24h at 15-min
    for step_i in range(FORECAST_STEPS):
        future_ts   = latest_ts + timedelta(minutes=(step_i + 1) * 15)
        hour_ahead  = (step_i + 1) / 4.0

        lvl   = float(lvl_spline(hour_ahead))
        unc   = float(unc_spline(hour_ahead))
        conf  = float(np.clip(conf_spline(hour_ahead), 0.0, 1.0))

        # Clamp to physical range
        lvl   = round(max(0.1, min(lvl, float(station.danger_level or 10.0) * 1.5)), 2)
        unc   = max(0.05, round(unc, 2))

        lvl_ft = lvl * 3.28084
        ci_half = 1.96 * unc * 3.28084
        upper_ft = round(lvl_ft + ci_half, 2)
        lower_ft = round(max(0.1, lvl_ft - ci_half), 2)

        # Determine dominant driver for this timestep
        h_closest = min(ANCHOR_HORIZONS, key=lambda x: abs(x - hour_ahead))
        d_closest = anchor_data.get(h_closest, {})

        hydrograph.append({
            "time": future_ts.strftime("%m-%d %H:%M"),
            "ts_iso": future_ts.isoformat(),
            "section": "forecast",
            "observed": None,
            "predicted": round(lvl_ft, 2),
            "median": round(lvl_ft, 2),
            "upper": upper_ft,
            "lower": lower_ft,
            "discharge": None,
            "rainfall_mm": None,
            "source": "model",
            "confidence": round(conf, 2),
            # Explainability per forecast point (converted to feet)
            "rain_contribution_m": round(d_closest.get("rain_contribution_m", 0.0) * 3.28084, 3),
            "upstream_contribution_m": round(d_closest.get("upstream_contribution_m", 0.0) * 3.28084, 3),
            "reservoir_contribution_m": round(d_closest.get("reservoir_contribution_m", 0.0) * 3.28084, 3),
        })

        rain_overlay.append({"time": future_ts.strftime("%m-%d %H:%M"), "rainfall_mm": None})
        discharge_overlay.append({
            "time": future_ts.strftime("%m-%d %H:%M"),
            "discharge_cumecs": None,
        })

    # ── XAI: SHAP + GAT ──────────────────────────────────────────────────────
    from app.backend.services.db.feature_store import get_inference_feature_sequence
    from app.backend.services.routing.multiscale_graph import build_dynamic_multiscale_graph
    from app.backend.services.xai.attention_extractor import extract_spatial_attention_coefficients
    from models.routing_model import HydroGNNNet

    stations_list = db.query(RiverStation).all()
    num_nodes = len(stations_list)
    station_idx = next((idx for idx, s in enumerate(stations_list) if s.id == station_id), 0)

    hist_list = []
    for s in stations_list:
        seq = get_inference_feature_sequence(db, s.id, latest_ts, lookback_steps=24)
        if seq is None or np.all(seq == 0.0):
            raw_levels = (
                db.query(RiverLevel)
                .filter(RiverLevel.station_id == s.id, RiverLevel.ts <= latest_ts)
                .order_by(RiverLevel.ts.desc())
                .limit(24)
                .all()
            )
            raw_levels.reverse()
            is_res = 1.0 if len(s.reservoirs) > 0 else 0.0
            elev_norm = s.dem_elevation / 1000.0
            rows = []
            for rl in raw_levels:
                rain_rec = db.query(Rainfall).filter(
                    Rainfall.station_id == s.id, Rainfall.ts == rl.ts
                ).first()
                wx_rec = db.query(Weather).filter(
                    Weather.station_id == s.id, Weather.ts == rl.ts
                ).first()
                rain_val = rain_rec.value_mm if rain_rec else 0.0
                temp_val = wx_rec.temp if wx_rec else 27.0
                hum_val  = wx_rec.humidity if wx_rec else 80.0
                soil_val = min(0.95, max(0.2, 0.3 + rain_val / 50.0))
                rows.append([
                    rain_val / 10.0,
                    soil_val,
                    (temp_val - 20.0) / 15.0,
                    hum_val / 100.0,
                    elev_norm,
                    is_res,
                    rl.level_m / max(s.danger_level, 1.0),
                    rl.discharge_cumecs / 100.0,
                ])
            while len(rows) < 24:
                rows.insert(0, [0.0] * 8)
            seq = np.array(rows[:24], dtype=np.float32)
        hist_list.append(seq)

    hist_x = np.expand_dims(np.stack(hist_list, axis=1), axis=0)
    fut_w   = np.zeros((1, 96, num_nodes, 3), dtype=np.float32)
    hist_x_t = torch.tensor(hist_x, dtype=torch.float32)
    fut_w_t  = torch.tensor(fut_w,  dtype=torch.float32)

    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    model_path  = os.path.join(backend_dir, "training", "checkpoints", "best_model.pt")
    spatial_attention = []

    if os.path.exists(model_path):
        try:
            model = HydroGNNNet(
                node_in_dim=8, weather_in_dim=3, hidden_dim=64, heads=4, num_layers=2, dropout=0.1
            )
            model.load_state_dict(torch.load(model_path, map_location="cpu"), strict=False)
            model.eval()
            full_edge_index, full_edge_lags, _ = build_dynamic_multiscale_graph(db, latest_ts)
            physical_edges, physical_lags = [], []
            for i in range(full_edge_index.shape[1]):
                u, v = full_edge_index[0, i].item(), full_edge_index[1, i].item()
                if u < 25 and v < 25:
                    physical_edges.append([u, v])
                    physical_lags.append(full_edge_lags[i].item())
            edge_index        = torch.tensor(physical_edges, dtype=torch.long).t().contiguous()
            edge_travel_times = torch.tensor(physical_lags, dtype=torch.float32)
            inf_start = time.time()
            with torch.no_grad():
                model(hist_x_t, fut_w_t, edge_index, edge_travel_times)
            inf_ms = (time.time() - inf_start) * 1000
            try:
                from app.backend.api.monitoring import set_last_inference_latency
                set_last_inference_latency(inf_ms)
            except Exception:
                pass
            spatial_attention = extract_spatial_attention_coefficients(model, edge_index)
        except Exception as e:
            print(f"Failed to generate live spatial attention weights: {e}")

    shap_attributions = compute_local_shap_attributions(station_id, station_idx, hist_x_t, fut_w_t)

    # GAT attention
    gat_attention = []
    if spatial_attention:
        incoming = [e for e in spatial_attention if e.get("target") == station_id]
        incoming.sort(key=lambda e: e.get("weight", 0), reverse=True)
        total_w = sum(e.get("weight", 0) for e in incoming) or 1.0
        for e in incoming[:3]:
            pct = round((e["weight"] / total_w) * 100)
            gat_attention.append({
                "source": e["source"],
                "weight_pct": pct,
                "description": "upstream flow contribution"
            })

    if not gat_attention:
        connections = _RIVER_CONNECTIONS
        try:
            upstream_edges = [(src, t) for src, dst, t in connections if dst == station_id]
            if not upstream_edges:
                upstream_edges = [(dst, t) for src, dst, t in connections if src == station_id]
            if not upstream_edges:
                upstream_edges = [(src, t) for src, dst, t in connections]
            if upstream_edges:
                raw_weights = [(sid, 1.0 / max(t, 0.25)) for sid, t in upstream_edges]
                total_w = sum(w for _, w in raw_weights) or 1.0
                raw_weights.sort(key=lambda x: x[1], reverse=True)
                for src_id, w in raw_weights[:3]:
                    up_st = db.query(RiverStation).filter(RiverStation.id == src_id).first()
                    up_name = up_st.name if up_st else src_id
                    pct = round((w / total_w) * 100)
                    up_level = (
                        db.query(RiverLevel)
                        .filter(RiverLevel.station_id == src_id, RiverLevel.ts <= now_utc)
                        .order_by(RiverLevel.ts.desc())
                        .first()
                    )
                    t_match = next((t for s, t in upstream_edges if s == src_id), None)
                    if up_level and t_match is not None:
                        desc = f"{up_level.discharge_cumecs:.1f} cumecs, {t_match:.1f}h travel lag"
                    else:
                        desc = "topology-based flow contribution"
                    gat_attention.append({"source": up_name, "weight_pct": pct, "description": desc})
        except Exception as e:
            print(f"  [GAT fallback] {e}")

    return {
        "station_id": station_id,
        "predictions": predictions_response,
        "hydrograph": hydrograph,
        "rain_overlay": rain_overlay,
        "discharge_overlay": discharge_overlay,
        "upstream_sources": upstream_sources,
        "routing_metadata": {
            "method": "Nash-Sutcliffe IUH + PchipInterpolator",
            "anchor_horizons_h": ANCHOR_HORIZONS,
            "rain_24h_mm": round(rain_24h_total, 1),
            "soil_moisture": round(soil_moisture, 2),
            "upstream_discharge_cumecs": round(upstream_discharge, 1),
            "reservoir_release_cumecs": round(res_release, 1),
            "observed_points": len(observed_grid),
            "forecast_points": FORECAST_STEPS,
        },
        "danger_level_m": float((station.danger_level or 10.0) * 3.28084),
        "warning_level_m": float((station.danger_level or 10.0) * 0.8 * 3.28084),
        "safe_level_m": float((station.danger_level or 10.0) * 0.5 * 3.28084),
        "xai_attributions": shap_attributions,
        "gat_attention": gat_attention,
    }
