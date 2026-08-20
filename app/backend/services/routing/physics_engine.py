import math
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.backend.services.db.models import RiverStation, RiverLevel
from datasets.simulator import CONNECTIONS, STATIONS

# Mapping of stations to districts for routing affected zones
STATION_DISTRICTS = {s["id"]: s["basin"] + " District" for s in STATIONS}

def compute_flow_velocity(level_m: float, slope: float, roughness: float = 0.035) -> float:
    """
    Computes river velocity using Manning's equation.
    V = (1/n) * Rh^(2/3) * S^(1/2)
    """
    # Estimate hydraulic radius Rh based on channel water level depth
    # Rh is approximated by depth for wide natural channels
    rh = max(0.1, 0.4 + level_m * 0.3)
    
    # Avoid zero or negative slopes
    s_val = max(0.0001, slope)
    
    velocity = (1.0 / roughness) * (rh ** (2.3 / 3.0)) * math.sqrt(s_val)
    # Clamp to realistic bounds (0.2 m/s to 4.5 m/s)
    return max(0.2, min(4.5, velocity))

def compute_travel_time_hours(length_km: float, velocity_m_s: float) -> float:
    """
    Computes wave travel time in hours.
    """
    if velocity_m_s <= 0:
        return 24.0
    seconds = (length_km * 1000.0) / velocity_m_s
    hours = seconds / 3600.0
    # Clamp travel time (0.25h to 36h)
    return max(0.25, min(36.0, hours))

def solve_reach_routing(db: Session, upstream_id: str, upstream_level: float, current_ts: datetime):
    """
    Solves flood routing parameters downstream from an upstream station.
    Trace downstream confluences, calculate arrival sequence, velocities, and expected peak times.
    """
    routing_results = []
    
    # Trace direct downstream connections
    downstream_connections = [conn for conn in CONNECTIONS if conn[0] == upstream_id]
    
    for src, dst, base_travel_time in downstream_connections:
        # Resolve reach attributes
        # Find elevation difference to estimate channel slope
        up_station = db.query(RiverStation).filter(RiverStation.id == src).first()
        down_station = db.query(RiverStation).filter(RiverStation.id == dst).first()
        
        if not up_station or not down_station:
            continue
            
        elev_diff = max(0.1, up_station.dem_elevation - down_station.dem_elevation)
        
        # Base length: base_travel_time * average velocity (e.g. 1.2 m/s)
        # Length in meters = travel_time_hours * 3600 * 1.2
        length_km = (base_travel_time * 3600.0 * 1.2) / 1000.0
        slope = elev_diff / (length_km * 1000.0)
        
        # Recalculate velocity dynamically
        velocity = compute_flow_velocity(upstream_level, slope)
        lag_hours = compute_travel_time_hours(length_km, velocity)
        
        arrival_ts = current_ts + timedelta(hours=lag_hours)
        
        routing_results.append({
            "upstream_station": src,
            "downstream_station": dst,
            "downstream_name": down_station.name,
            "affected_district": STATION_DISTRICTS.get(dst, "Tamil Nadu Region"),
            "base_lag_hours": base_travel_time,
            "dynamic_lag_hours": round(lag_hours, 2),
            "flow_velocity_m_s": round(velocity, 2),
            "expected_arrival_time": arrival_ts.strftime("%Y-%m-%d %H:%M:%S"),
            "distance_km": round(length_km, 1)
        })
        
    return routing_results
