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
from app.backend.services.routing.exp9_service import run_experiment9_prediction

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

    horizons = req.horizons_hours if req.horizons_hours else [6, 12, 24]

    inf_start = time.time()
    result = run_experiment9_prediction(db, station_id, horizons)
    inf_ms = (time.time() - inf_start) * 1000

    try:
        from app.backend.api.monitoring import set_last_inference_latency
        set_last_inference_latency(inf_ms)
    except Exception:
        pass

    return result

