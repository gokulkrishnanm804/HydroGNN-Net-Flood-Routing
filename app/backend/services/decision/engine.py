import os
from sqlalchemy.orm import Session
from app.backend.services.logging_manager import alerts_logger

# Static resources mapping for shelter locations in Tamil Nadu
DISTRICT_SHELTERS = {
    "SALEM_DIST": ["Mettur Welfare Center", "Salem Town Community Hall"],
    "ERODE_DIST": ["Bhavani RDO Office Shelter", "Erode District Indoor Stadium"],
    "TRICHY_DIST": ["Srirangam Girls School Hall", "Grand Anicut Community Center"],
    "TIRUPPUR_DIST": ["Dharapuram Municipal School", "Amaravathi Forest quarters"],
    "MADURAI_DIST": ["Madurai Corporation Hall", "Anaiyur Flood Relief Camp"],
    "TIRUNELVELI_DIST": ["Cheranmahadevi Union Hall", "Tirunelveli Exhibition Grounds"],
    "THOOTHUKUDI_DIST": ["Srivaikuntam Taluk Office", "Authoor Welfare Center"]
}

# Static infrastructure risk roads mapping
STATION_ROAD_RISKS = {
    "METTUR": "SH-20 Salem-Mettur High Road near Cauvery bridge",
    "ERODE": "NH-544 Salem-Cochin bypass underpass near Erode",
    "TRICHY": "SH-22 Trichy-Chidambaram road near Grand Anicut",
    "BHAVANISAGAR": "Bhavanisagar-Bannari ghat road low-lying segments",
    "VAIGAI_DAM": "Theni-Madurai SH-13 road near dam outlet channel",
    "TIRUNELVELI": "Tirunelveli Junction-Kokkirakulam bypass under bridge",
    "SRIVAIKUNTAM": "SH-75 Srivaikuntam-Tiruchendur road near Anicut channel"
}

def generate_decision_support(predictions_list: list) -> dict:
    """
    Computes evacuation rankings, reservoir releases, shelter allocations, and road closures.
    Args:
        predictions_list: List of dictionaries with station_id, level, discharge, severity, storage_pct
    """
    reservoirs = []
    evacuation_rankings = []
    road_closures = []
    shelter_allocations = {}
    
    # Track risk level count per district for ranking
    district_risks = {}
    
    for pred in predictions_list:
        st_id = pred["station_id"]
        level = pred.get("predicted_level", 0.0)
        discharge = pred.get("predicted_discharge", 0.0)
        sev = pred.get("severity", "Safe")
        storage_pct = pred.get("storage_pct", 0.0)
        basin = pred.get("basin", "Cauvery")
        
        # 1. Reservoir Gate Controls
        if storage_pct > 0.0:
            rec_action = "Maintain current gates structure"
            priority = "Routine"
            
            if storage_pct > 90.0 or level > pred.get("danger_level", 100.0) * 0.95:
                rec_action = f"Alert: Open gates fully. Increase spillway discharge by {round(discharge * 0.4, 1)} cumecs to prevent overtopping."
                priority = "CRITICAL"
            elif storage_pct > 80.0:
                rec_action = f"Precautionary: Open gates partially. Discharge {round(discharge * 0.15, 1)} cumecs to secure 15% cushion."
                priority = "WARNING"
                
            reservoirs.append({
                "reservoir_id": st_id,
                "storage_pct": round(storage_pct, 1),
                "predicted_inflow": round(discharge, 1),
                "recommended_action": rec_action,
                "priority_level": priority
            })
            
        # 2. Road & Infrastructure Closures
        if sev in ["High", "Severe"] and st_id in STATION_ROAD_RISKS:
            road_closures.append({
                "road": STATION_ROAD_RISKS[st_id],
                "reason": f"High risk prediction near {st_id} confluence (Level: {round(level, 2)}m)",
                "status": "CLOSED" if sev == "Severe" else "MONITOR"
            })
            
        # 3. Evacuation Rankings calculation
        dist_key = f"{basin.upper()}_DIST"
        if dist_key not in district_risks:
            district_risks[dist_key] = {"Severe": 0, "High": 0, "Moderate": 0, "Low": 0, "max_score": 0.0}
            
        # Weighting risk level
        weight = 0.0
        if sev == "Severe":
            district_risks[dist_key]["Severe"] += 1
            weight = 4.0
        elif sev == "High":
            district_risks[dist_key]["High"] += 1
            weight = 3.0
        elif sev == "Moderate":
            district_risks[dist_key]["Moderate"] += 1
            weight = 2.0
        elif sev == "Low":
            district_risks[dist_key]["Low"] += 1
            weight = 1.0
            
        # Store maximum score for sorting
        district_risks[dist_key]["max_score"] = max(district_risks[dist_key]["max_score"], weight)
        
    # Build sorted evacuation ranking list
    sorted_dists = sorted(
        district_risks.items(),
        key=lambda item: (item[1]["Severe"], item[1]["High"], item[1]["max_score"]),
        reverse=True
    )
    
    rank = 1
    for dist_id, stats in sorted_dists:
        sev_count = stats["Severe"] + stats["High"]
        if sev_count > 0:
            evac_status = "IMMEDIATE" if stats["Severe"] > 0 else "PREPARATION"
            evacuation_rankings.append({
                "rank": rank,
                "district": dist_id.replace("_DIST", " District").title(),
                "status": evac_status,
                "high_risk_stations_count": sev_count
            })
            rank += 1
            
            # Map shelters
            shelter_allocations[dist_id.replace("_DIST", " District").title()] = DISTRICT_SHELTERS.get(dist_id, ["Local School Center"])
            
    return {
        "reservoir_controls": reservoirs,
        "evacuation_rankings": evacuation_rankings,
        "road_closures": road_closures,
        "shelter_allocations": shelter_allocations,
        "emergency_response_level": "RED ALERT" if any(r["priority_level"] == "CRITICAL" for r in reservoirs) or len(evacuation_rankings) > 0 else "NORMAL"
    }
