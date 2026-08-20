import os
import json
import torch
from datetime import datetime
from sqlalchemy.orm import Session
from app.backend.services.db.models import RiverStation, RiverLevel
from app.backend.services.routing.physics_engine import solve_reach_routing
from datasets.simulator import CONNECTIONS, STATIONS

# Mapping of Station ID to Level 3 Districts
DISTRICT_CONFLUENCES = {
    "METTUR": "SALEM_DIST",
    "ERODE": "ERODE_DIST",
    "TRICHY": "TRICHY_DIST",
    "BHAVANISAGAR": "ERODE_DIST",
    "AMARAVATHI_DAM": "TIRUPPUR_DIST",
    "VAIGAI_DAM": "MADURAI_DIST",
    "MADURAI": "MADURAI_DIST",
    "PAPANASAM": "TIRUNELVELI_DIST",
    "AMBASAMUDRAM": "TIRUNELVELI_DIST",
    "TIRUNELVELI": "TIRUNELVELI_DIST",
    "SRIVAIKUNTAM": "THOOTHUKUDI_DIST"
}

# Mapping of Districts to Level 4 Villages
VILLAGE_CONNECTIONS = {
    "SALEM_DIST": ["METTUR_VILLAGE", "KOMARAPALAYAM"],
    "ERODE_DIST": ["ERODE_VILLAGE", "BHAVANI_TOWN_VILLAGE"],
    "TRICHY_DIST": ["TRICHY_VILLAGE", "SRIRANGAM_VILLAGE"],
    "TIRUPPUR_DIST": ["DHARAPURAM_VILLAGE", "MADATHUKULAM"],
    "MADURAI_DIST": ["MADURAI_VILLAGE", "ANAIYUR_VILLAGE"],
    "TIRUNELVELI_DIST": ["TIRUNELVELI_TOWN", "CHERANMAHADEVI"],
    "THOOTHUKUDI_DIST": ["SRIVAIKUNTAM_VILLAGE", "AUTHOOR"]
}

def get_multiscale_node_list(db: Session):
    """
    Constructs a unified, index-mapped node list across all 4 spatial scales.
    Returns:
        nodes: List of dicts representing all nodes in the unified graph.
        node_to_idx: Map of string node ID to integer graph index.
    """
    stations = db.query(RiverStation).all()
    
    nodes = []
    node_to_idx = {}
    
    # 1. Level 1 & 2: Gauges & Reservoirs
    for s in stations:
        is_reservoir = len(s.reservoirs) > 0
        node_type = "level1_reservoir" if is_reservoir else "level2_river_gauge"
        node_to_idx[s.id] = len(nodes)
        nodes.append({
            "id": s.id,
            "type": node_type,
            "elevation": s.dem_elevation,
            "lat": s.lat,
            "lon": s.lon
        })
        
    # 2. Level 3: Districts
    districts = sorted(list(set(DISTRICT_CONFLUENCES.values())))
    for d in districts:
        node_to_idx[d] = len(nodes)
        nodes.append({
            "id": d,
            "type": "level3_district",
            "elevation": 50.0, # Neutral elevation
            "lat": 11.0, "lon": 78.5 # Center placeholders
        })
        
    # 3. Level 4: Villages
    villages = []
    for v_list in VILLAGE_CONNECTIONS.values():
        villages.extend(v_list)
    villages = sorted(list(set(villages)))
    for v in villages:
        node_to_idx[v] = len(nodes)
        nodes.append({
            "id": v,
            "type": "level4_village",
            "elevation": 20.0,
            "lat": 10.8, "lon": 78.2
        })
        
    return nodes, node_to_idx

def build_dynamic_multiscale_graph(db: Session, current_ts: datetime):
    """
    Regenerates PyTorch Geometric edge_index and edge_travel_times tensors dynamically.
    Updates edge travel times using real-time physical routing parameters.
    """
    nodes, node_to_idx = get_multiscale_node_list(db)
    
    edge_list = []
    edge_lags = []
    
    # 1. Construct Level 1 & 2 direct connections with dynamic routing
    # Map connections to current level discharge lags
    for src, dst, base_lag in CONNECTIONS:
        # Resolve level at upstream station
        lvl_rec = db.query(RiverLevel).filter(
            RiverLevel.station_id == src,
            RiverLevel.ts == current_ts
        ).first()
        upstream_lvl = lvl_rec.level_m if lvl_rec else 1.0
        
        # Calculate dynamic lag
        routing_info = solve_reach_routing(db, src, upstream_lvl, current_ts)
        # Find matching destination
        lag = base_lag
        for info in routing_info:
            if info["downstream_station"] == dst:
                lag = info["dynamic_lag_hours"]
                break
                
        u_idx = node_to_idx[src]
        v_idx = node_to_idx[dst]
        edge_list.append([u_idx, v_idx])
        edge_lags.append(lag)
        
    # 2. Level 2 -> Level 3 (Gauges confluencing into Districts)
    for st_id, dist_id in DISTRICT_CONFLUENCES.items():
        u_idx = node_to_idx[st_id]
        v_idx = node_to_idx[dist_id]
        edge_list.append([u_idx, v_idx])
        edge_lags.append(0.5) # Fast 30-min administrative propagation delay
        
    # 3. Level 3 -> Level 4 (Districts flooding constituent Villages)
    for dist_id, v_list in VILLAGE_CONNECTIONS.items():
        u_idx = node_to_idx[dist_id]
        for village_id in v_list:
            v_idx = node_to_idx[village_id]
            edge_list.append([u_idx, v_idx])
            edge_lags.append(1.0) # 1 hour propagation lag target
            
    # Convert lists to PyTorch Geometric tensors
    edge_index = torch.tensor(edge_list, dtype=torch.long).t().contiguous()
    edge_travel_times = torch.tensor(edge_lags, dtype=torch.float32)
    
    return edge_index, edge_travel_times, node_to_idx
