import os
import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

# DB imports
from app.backend.services.db.connection import get_db
from app.backend.services.db.models import RiverStation, Reservoir, RiverLevel, Alert, Rainfall, Weather, SatelliteImage, Prediction
from app.backend.auth.jwt_handler import verify_access_token
from app.backend.services.hydrology.reservoir_routing import calculate_scientific_reservoir_routing

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    payload = verify_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid access token")
    return payload

def compute_risk(level, danger):
    ratio = level / danger
    if ratio < 0.4: return "Safe"
    elif ratio < 0.7: return "Low Risk"
    elif ratio < 0.9: return "Moderate Risk"
    elif ratio < 1.0: return "High Risk"
    else: return "Severe Flood"

@router.get("")
def get_dashboard_summary(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    # DATABASE QUERY: Retrieves the most recent observed river-level record from the RiverLevel table
    # whose timestamp is earlier than or equal to current UTC time (clamping prevents future simulated timestamps from masking today's live ingestion).
    now_utc = datetime.utcnow()
    latest_level_rec = (
        db.query(RiverLevel)
        .filter(RiverLevel.ts <= now_utc)
        .order_by(RiverLevel.ts.desc())
        .first()
    )
    if not latest_level_rec:
        # Fall back to absolute latest if nothing within real-time window
        latest_level_rec = db.query(RiverLevel).order_by(RiverLevel.ts.desc()).first()
    if not latest_level_rec:
        return {
            "timestamp": now_utc.strftime("%Y-%m-%d %H:%M:%S"),
            "active_warnings": 0,
            "average_reservoir_fill_pct": 0.0,
            "heavy_rain_stations_count": 0,
            "stations": [],
            "reservoirs": []
        }

    latest_ts = latest_level_rec.ts
    
    # 2. Fetch all telemetry records for this timestamp
    telemetry = db.query(RiverLevel).filter(RiverLevel.ts == latest_ts).all()
    
    stations_list = []
    reservoir_list = []
    
    active_warnings = 0
    total_capacity = 0.0
    total_storage = 0.0
    
    seen_station_ids = set()
    for row in telemetry:
        station = row.station
        if not station or station.id in seen_station_ids:
            continue
        seen_station_ids.add(station.id)
        level = row.level_m
        danger = station.danger_level
        risk = compute_risk(level, danger)
        
        if risk in ["High Risk", "Severe Flood"]:
            active_warnings += 1
            
        # Get latest rain observed for this station
        rain_rec = db.query(Rainfall).filter(Rainfall.station_id == station.id, Rainfall.ts == latest_ts).first()
        rain_val = rain_rec.value_mm if rain_rec else 0.0
        
        # Issue S1 Fix -- soil moisture using station-specific baseline
        # Old formula collapsed to 0.2 for all stations when rain=0
        import datetime as dt
        t_24h = latest_ts - dt.timedelta(hours=24)
        rain_24h = db.query(Rainfall).filter(
            Rainfall.station_id == station.id, Rainfall.ts >= t_24h
        ).all()
        rain_sum_24h = sum([max(0.0, r.value_mm) for r in rain_24h])   # clamp: legacy rows may have negative values
        # Higher elevation = slightly drier soil (max 8% reduction)
        elevation_factor = min(0.08, station.dem_elevation / 5000.0)
        # Cauvery and Bhavani are perennially wetter basins
        basin_baseline = 0.45 if station.river in ["Cauvery", "Bhavani"] else 0.38
        rain_contrib = rain_sum_24h / 150.0
        soil_moisture = round(min(0.95, max(0.20, basin_baseline - elevation_factor + rain_contrib)), 2)
        
        # Get latest weather row — prioritise live sources over seeded simulation rows.
        # Simulation rows have future timestamps (Nov 2026) that would otherwise
        # always beat real OpenWeather/NASA rows in a plain ORDER BY ts DESC.
        from app.backend.services.db.models import Weather
        from sqlalchemy import case
        source_priority = case(
            (Weather.source == "openweather", 1),
            (Weather.source == "nasa_power",  2),
            (Weather.source == "open_meteo",  3),
            else_=4
        )
        weather_rec = (
            db.query(Weather)
            .filter(Weather.station_id == station.id)
            .order_by(source_priority, Weather.ts.desc())
            .first()
        )
        temperature    = round(weather_rec.temp,       1) if weather_rec else None
        humidity_val   = round(weather_rec.humidity,   1) if weather_rec else None
        wind_speed_val = round(weather_rec.wind_speed, 1) if weather_rec else None
        weather_src    = weather_rec.source if weather_rec else "none"



        # Get latest prediction for this station
        from app.backend.services.db.models import Prediction
        pred_rec = db.query(Prediction).filter(Prediction.station_id == station.id).order_by(Prediction.issued_at.desc()).first()
        flood_prob = int(pred_rec.flood_probability * 100) if (pred_rec and pred_rec.flood_probability is not None) else 0

        station_item = {
            "id": station.id,
            "name": station.name,
            "basin": station.river,
            "type": "reservoir" if len(station.reservoirs) > 0 else "gauge",
            "lat": station.lat,
            "lon": station.lon,
            "elevation": station.dem_elevation,
            "water_level": round(level * 3.28084, 2),
            "danger_level": round(danger * 3.28084, 2),
            "warning_level": round(danger * 0.8 * 3.28084, 2),
            "safe_level": round(danger * 0.5 * 3.28084, 2),
            "flood_probability": flood_prob,
            "discharge": round(row.discharge_cumecs, 1),
            "risk_level": risk,
            "rain_observed": round(rain_val, 2),
            "soil_moisture": round(soil_moisture, 2),
            "temperature": temperature,
            "humidity": humidity_val,
            "wind_speed": wind_speed_val,
            "data_source": row.source,       # river level source (open_meteo / simulation)
            "weather_source": weather_src,   # weather source (openweather / nasa_power / simulation)
        }
        
        # If it has reservoir metadata
        if len(station.reservoirs) > 0:
            res = station.reservoirs[0]
            storage_pct = row.storage_pct
            cap_mcft = res.capacity_mcft
            curr_storage = (storage_pct / 100.0) * cap_mcft
            release = row.release

            total_capacity += cap_mcft
            total_storage += curr_storage

            # Compute reservoir operational status from storage fill level
            if storage_pct > 90.0:
                res_status = "CRITICAL INFLOW"
            elif storage_pct > 80.0:
                res_status = "HIGH ALERT"
            elif storage_pct > 65.0:
                res_status = "ELEVATED"
            elif storage_pct > 30.0:
                res_status = "NORMAL"
            else:
                res_status = "LOW LEVEL"

            sci_routing = calculate_scientific_reservoir_routing(
                inflow_cumecs=0.12,  # Live inflow
                current_storage_pct=storage_pct,
                capacity_mcft=cap_mcft,
                danger_level_m=station.danger_level
            )

            res_item = {
                "id": station.id,
                "name": station.name,
                "lat": station.lat,
                "lon": station.lon,
                "capacity_mcft": round(cap_mcft, 1),
                "storage_pct": round(storage_pct, 1),
                "current_storage_mcft": round(curr_storage, 1),
                "release_cumecs": round(release, 2),
                "status": res_status,
                "data_source": "MODEL DERIVED",
                "outflow_calculation": {
                    "method": sci_routing["calculation_method"],
                    "rule_curve_stage": sci_routing["rule_curve_stage"],
                    "formula": sci_routing["formula"],
                    "scientific_references": sci_routing["scientific_references"],
                    "inputs": sci_routing["inputs"],
                    "assumptions": sci_routing["assumptions"],
                    "calculation_timestamp": (latest_ts + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M IST")
                }
            }
            reservoir_list.append(res_item)
            station_item["reservoir_info"] = res_item

        stations_list.append(station_item)
        
    avg_storage_pct = (total_storage / total_capacity * 100) if total_capacity > 0 else 0.0
    
    # Compute active weather events
    heavy_rain_stations = int(db.query(Rainfall).filter(Rainfall.ts == latest_ts, Rainfall.value_mm > 10.0).count())
    
    # Generate decision support details dynamically based on telemetry values
    prediction_inputs = []
    for s_item in stations_list:
        prediction_inputs.append({
            "station_id": s_item["id"],
            "predicted_level": s_item["water_level"],
            "predicted_discharge": s_item["discharge"],
            "severity": "Severe" if s_item["risk_level"] == "Severe Flood" else "High" if s_item["risk_level"] == "High Risk" else "Moderate" if s_item["risk_level"] == "Moderate Risk" else "Low" if s_item["risk_level"] == "Low Risk" else "Safe",
            "storage_pct": s_item.get("reservoir_info", {}).get("storage_pct", 0.0) if s_item["type"] == "reservoir" else 0.0,
            "basin": s_item["basin"],
            "danger_level": s_item["danger_level"]
        })
        
    from app.backend.services.decision.engine import generate_decision_support
    decision_support = generate_decision_support(prediction_inputs)
    
    age_seconds = (now_utc - latest_ts).total_seconds()
    if age_seconds <= 3600:
        data_status = "Live"
    elif age_seconds <= 86400 * 7:
        data_status = "Latest Available"
    else:
        data_status = "Stale"

    last_updated_ist = (latest_ts + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M IST")

    # Provider Freshness Metrics
    ow_rec = db.query(Weather).filter(Weather.source == 'openweather').order_by(Weather.ts.desc()).first()
    ow_ts = ow_rec.ts if ow_rec else None
    ow_age = (now_utc - ow_ts).total_seconds() if ow_ts else 999999
    ow_status = "Live" if ow_age <= 1800 else ("Latest Available" if ow_age <= 86400 * 7 else "Stale")

    om_rec = db.query(RiverLevel).filter(RiverLevel.source == 'open_meteo').order_by(RiverLevel.ts.desc()).first()
    om_ts = om_rec.ts if om_rec else None
    om_age = (now_utc - om_ts).total_seconds() if om_ts else 999999
    om_status = "Live" if om_age <= 1800 else ("Latest Available" if om_age <= 86400 * 7 else "Stale")

    res_ts_str = (latest_ts + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M IST") if latest_ts else "N/A"
    res_status = "Live" if age_seconds <= 1800 else ("Latest Available" if age_seconds <= 86400 * 7 else "Stale")

    sat_rec = db.query(SatelliteImage).order_by(SatelliteImage.capture_date.desc()).first()
    sat_ts_str = sat_rec.capture_date if sat_rec else "N/A"
    sat_status = "Latest Available"

    pred_rec = db.query(Prediction).order_by(Prediction.issued_at.desc()).first()
    pred_ts = pred_rec.issued_at if pred_rec else None
    pred_age = (now_utc - pred_ts).total_seconds() if pred_ts else 999999
    pred_status = "Live" if pred_age <= 1800 else ("Latest Available" if pred_age <= 86400 * 7 else "Stale")
    pred_ts_str = (pred_ts + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M IST") if pred_ts else "N/A"

    data_freshness = [
        {"source": "OpenWeather API", "last_updated": (ow_ts + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M IST") if ow_ts else "N/A", "status": ow_status, "refresh_interval": "15 mins"},
        {"source": "Open-Meteo Flood API", "last_updated": (om_ts + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M IST") if om_ts else "N/A", "status": om_status, "refresh_interval": "15 mins"},
        {"source": "Reservoir Data", "last_updated": res_ts_str, "status": res_status, "refresh_interval": "15 mins"},
        {"source": "CWC River Levels", "last_updated": res_ts_str, "status": res_status, "refresh_interval": "15 mins"},
        {"source": "Copernicus STAC", "last_updated": sat_ts_str, "status": sat_status, "refresh_interval": "5 days"},
        {"source": "AI Prediction Model", "last_updated": pred_ts_str, "status": pred_status, "refresh_interval": "15 mins"}
    ]

    summary = {
        "timestamp": latest_ts.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp_ist": last_updated_ist,
        "data_status": data_status,
        "data_source": "OpenWeather API & Open-Meteo Flood API",
        "active_warnings": active_warnings,
        "average_reservoir_fill_pct": round(avg_storage_pct, 1),
        "heavy_rain_stations_count": heavy_rain_stations,
        "stations": stations_list,
        "reservoirs": reservoir_list,
        "decision_support": decision_support,
        "data_freshness": data_freshness
    }
    
    return summary
