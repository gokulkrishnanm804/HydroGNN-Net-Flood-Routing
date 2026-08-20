import os
import json
import numpy as np
from datetime import datetime
from sqlalchemy.orm import Session
from app.backend.services.db.models import FeatureStore, RiverStation
from app.backend.services.logging_manager import database_logger

SCALING_STATS = None

def load_scaling_stats():
    global SCALING_STATS
    if SCALING_STATS is not None:
        return SCALING_STATS
        
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    project_dir = os.path.dirname(os.path.dirname(backend_dir))
    stats_path = os.path.join(project_dir, "training", "checkpoints", "scaling_stats.json")
    
    if os.path.exists(stats_path):
        with open(stats_path, "r") as f:
            SCALING_STATS = json.load(f)
    else:
        # Default scaling stats if not trained yet
        SCALING_STATS = {
            "means": {"rain_observed": 0.5, "water_level": 5.0, "discharge": 50.0},
            "stds": {"rain_observed": 2.5, "water_level": 3.0, "discharge": 75.0}
        }
    return SCALING_STATS

def push_to_feature_store(db: Session, station_id: str, ts: datetime, rain: float, level: float, discharge: float, soil_moisture: float, split_type: str = "inference", version_id: str = None):
    """
    Normalizes raw features and writes them to the Feature Store table.
    """
    stats = load_scaling_stats()
    
    # Z-Score normalization
    def scale(col, val):
        m = stats["means"].get(col, 0.0)
        s = stats["stds"].get(col, 1.0)
        return (val - m) / (s if s > 0 else 1.0)
        
    rain_norm = scale("rain_observed", rain)
    level_norm = scale("water_level", level)
    discharge_norm = scale("discharge", discharge)
    
    feat_id = f"FEAT_{station_id}_{ts.strftime('%Y%m%d%H%M')}"
    
    # Check if already exists to avoid duplication
    exists = db.query(FeatureStore).filter(FeatureStore.feature_id == feat_id).first()
    if exists:
        return exists
        
    feat_rec = FeatureStore(
        feature_id=feat_id,
        station_id=station_id,
        ts=ts,
        rain_norm=float(rain_norm),
        level_norm=float(level_norm),
        discharge_norm=float(discharge_norm),
        soil_moisture=float(soil_moisture),
        split_type=split_type,
        version_id=version_id
    )
    db.add(feat_rec)
    db.commit()
    return feat_rec

def get_inference_feature_sequence(db: Session, station_id: str, ts: datetime, lookback_steps: int = 24):
    """
    Queries the Feature Store for the lookback sequence of normalized features.
    Returns a numpy array of shape [lookback_steps, 8].
    """
    station = db.query(RiverStation).filter(RiverStation.id == station_id).first()
    if not station:
        return None
        
    recs = db.query(FeatureStore).filter(
        FeatureStore.station_id == station_id,
        FeatureStore.ts <= ts
    ).order_by(FeatureStore.ts.desc()).limit(lookback_steps).all()
    
    if len(recs) < lookback_steps:
        # Pad with zeros if insufficient history
        padding_len = lookback_steps - len(recs)
        pad = [[0.0] * 8 for _ in range(padding_len)]
        data = pad
        recs.reverse() # chronological
    else:
        recs.reverse()
        data = []
        
    max_elev = 1000.0 # elevation scale target
    is_res = 1.0 if len(station.reservoirs) > 0 else 0.0
    
    # Extract station physical constants
    elev = station.dem_elevation
    
    for r in recs:
        # Build 8-channel feature vector:
        # [rain_norm, soil_moisture, temp, humidity, elevation, is_reservoir, water_level_norm, discharge_norm]
        data.append([
            r.rain_norm,
            r.soil_moisture,
            0.0, # temp (neutral)
            0.0, # humidity (neutral)
            elev / max_elev,
            is_res,
            r.level_norm,
            r.discharge_norm
        ])
        
    return np.array(data)
