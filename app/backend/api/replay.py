import os
import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.backend.services.db.connection import get_db
from app.backend.services.db.models import RiverLevel, Prediction, RiverStation

router = APIRouter(prefix="/replay", tags=["replay"])

# Static list of historical Chennai/TN flood scenarios
FLOOD_SCENARIOS = {
    "2015 Chennai Flood": {
        "description": "Extreme northeast monsoon deluge causing massive Chembarambakkam reservoir release and Adyar river overflow.",
        "peak_multiplier": 2.8,
        "duration_days": 3,
        "critical_stations": ["METTUR", "TRICHY", "TIRUNELVELI"]
    },
    "2021 Chennai Flood": {
        "description": "Heaviest single-day rain since 2015 flooding roads, administrative districts, and low-lying delta cities.",
        "peak_multiplier": 1.9,
        "duration_days": 2,
        "critical_stations": ["GOBICHETTIPALAYAM", "ERODE"]
    },
    "2023 Tamil Nadu Flood": {
        "description": "Cyclone Michaung triggered record-breaking precipitation in southern districts including Vaigai and Tamirabarani basins.",
        "peak_multiplier": 2.4,
        "duration_days": 4,
        "critical_stations": ["PAPANASAM", "MADURAI", "SRIVAIKUNTAM"]
    }
}

@router.get("/events")
def get_replay_events():
    """
    Returns available historical flood scenarios.
    """
    return [
        {
            "name": name,
            "description": info["description"],
            "duration_days": info["duration_days"],
            "critical_stations": info["critical_stations"]
        }
        for name, info in FLOOD_SCENARIOS.items()
    ]

from pydantic import BaseModel
class TriggerReplayRequest(BaseModel):
    event_name: str
    station_id: str

@router.post("/trigger")
def trigger_replay_simulation(req: TriggerReplayRequest, db: Session = Depends(get_db)):
    """
    Simulates a historical flood event step-by-step for a target station,
    generating comparison sequences between predicted level trends and actual observed levels.
    """
    event = req.event_name
    st_id = req.station_id.upper()
    
    if event not in FLOOD_SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Scenario '{event}' not found.")
        
    station = db.query(RiverStation).filter(RiverStation.id == st_id).first()
    if not station:
        raise HTTPException(status_code=404, detail=f"Station '{st_id}' not found.")
        
    scenario = FLOOD_SCENARIOS[event]
    mult = scenario["peak_multiplier"]
    
    # Generate 12-hour simulation timeline (hourly steps)
    start_ts = datetime(2026, 11, 1, 0, 0, 0)
    comparison_data = []
    
    danger_lvl = station.danger_level
    
    for hour in range(12):
        ts = start_ts + timedelta(hours=hour)
        
        # Simulated actual level: rises to peak, then declines slightly
        # Normal profile normalized around danger level
        if hour < 6:
            # Rise phase
            actual_lvl = 0.5 * danger_lvl + (hour / 6.0) * (danger_lvl * mult - 0.5 * danger_lvl)
        else:
            # Recede phase
            actual_lvl = danger_lvl * mult - ((hour - 6) / 6.0) * (0.3 * danger_lvl * mult)
            
        # Add slight noise
        import random
        actual_lvl += random.uniform(-0.15, 0.15)
        actual_lvl = round(max(0.2, actual_lvl), 2)
        
        # Predicted level: slightly lags and estimates uncertainty bounds
        predicted_lvl = actual_lvl + random.uniform(-0.4, 0.2)
        predicted_lvl = round(max(0.15, predicted_lvl), 2)
        
        unc = 0.15 + (hour / 12.0) * 0.35
        
        comparison_data.append({
            "timestamp": ts.strftime("%H:%M"),
            "observed_actual": actual_lvl,
            "predicted_gnn": predicted_lvl,
            "upper_bound": round(predicted_lvl + 1.96 * unc, 2),
            "lower_bound": round(max(0.1, predicted_lvl - 1.96 * unc), 2)
        })
        
    return {
        "event_name": event,
        "station_id": st_id,
        "simulation_steps_count": len(comparison_data),
        "comparison_timeline": comparison_data
    }
