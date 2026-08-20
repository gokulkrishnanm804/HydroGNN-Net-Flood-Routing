import os
from datetime import datetime
from sqlalchemy.orm import Session
from app.backend.services.db.models import RiverLevel, Rainfall, Weather
from app.backend.services.logging_manager import database_logger

def validate_telemetry_data(db: Session, station_id: str, ts: datetime, rain_mm: float, level_m: float, discharge: float):
    """
    Validates incoming telemetry readings.
    Returns:
        quality_score (float 0-1)
        missing_count (int)
        status (str): "VALID", "CLEANED", or "CORRUPTED"
        cleaned_values (dict): containing cleaned rain, level, and discharge
    """
    missing_count = 0
    anomalies = []
    
    # 1. Null / None Check
    if rain_mm is None:
        rain_mm = 0.0
        missing_count += 1
        anomalies.append("Null rainfall replaced with 0.0")
    if level_m is None:
        level_m = 0.5
        missing_count += 1
        anomalies.append("Null level replaced with 0.5")
    if discharge is None:
        discharge = 10.0
        missing_count += 1
        anomalies.append("Null discharge replaced with 10.0")
        
    # 2. Negative Range Verification
    cleaned_rain = max(0.0, rain_mm)
    if rain_mm < 0:
        anomalies.append(f"Negative rainfall ({rain_mm}mm) capped to 0.0")
        
    cleaned_level = max(0.0, level_m)
    if level_m < 0:
        anomalies.append(f"Negative water level ({level_m}m) capped to 0.0")
        
    cleaned_discharge = max(0.0, discharge)
    if discharge < 0:
        anomalies.append(f"Negative discharge ({discharge} cumecs) capped to 0.0")
        
    # 3. Outlier check (Rain > 250mm/15min, or Level > 100m)
    if cleaned_rain > 250.0:
        cleaned_rain = 250.0
        anomalies.append(f"Rainfall outlier ({rain_mm}mm) capped to 250.0")
    if cleaned_level > 80.0:
        cleaned_level = 80.0
        anomalies.append(f"Water level outlier ({level_m}m) capped to 80.0")
        
    # 4. Stuck Sensor / Zero Variance Check
    # Fetch last 8 records (2 hours) of water levels for this station
    recent_recs = db.query(RiverLevel).filter(
        RiverLevel.station_id == station_id,
        RiverLevel.ts < ts
    ).order_by(RiverLevel.ts.desc()).limit(8).all()
    
    if len(recent_recs) >= 8:
        recent_lvls = [r.level_m for r in recent_recs]
        if all(x == level_m for x in recent_lvls):
            # Level hasn't budged by even 1mm in 2 hours
            anomalies.append(f"Sensor flatlining warning: Stuck level value {level_m}m")
            
    # Calculate Quality Score
    num_anomalies = len(anomalies)
    quality_score = max(0.0, 1.0 - (num_anomalies * 0.15) - (missing_count * 0.25))
    
    if num_anomalies > 0 or missing_count > 0:
        database_logger.warning(
            f"Data Quality anomalies detected for station {station_id} at {ts}: {'; '.join(anomalies)}. Quality score: {quality_score}"
        )
        status = "CLEANED" if quality_score > 0.4 else "CORRUPTED"
    else:
        status = "VALID"
        
    return quality_score, missing_count, status, {
        "rain": cleaned_rain,
        "level": cleaned_level,
        "discharge": cleaned_discharge
    }
