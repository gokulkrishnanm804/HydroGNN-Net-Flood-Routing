import os
import math
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Define the station metadata for the major basins in Tamil Nadu
STATIONS = [
    # --- CAUVERY BASIN ---
    {"id": "METTUR", "name": "Mettur Reservoir", "basin": "Cauvery", "type": "reservoir", "lat": 11.78, "lon": 77.80, "elevation": 210.0, "capacity_mcft": 93470.0, "danger_level": 120.0},
    {"id": "ERODE", "name": "Erode Gauge", "basin": "Cauvery", "type": "gauge", "lat": 11.35, "lon": 77.73, "elevation": 160.0, "capacity_mcft": 0.0, "danger_level": 8.0},
    {"id": "KARUR", "name": "Karur Gauge", "basin": "Cauvery", "type": "gauge", "lat": 10.95, "lon": 78.08, "elevation": 122.0, "capacity_mcft": 0.0, "danger_level": 7.5},
    {"id": "TRICHY", "name": "Tiruchirappalli Grand Anicut", "basin": "Cauvery", "type": "gauge", "lat": 10.83, "lon": 78.68, "elevation": 85.0, "capacity_mcft": 0.0, "danger_level": 12.0},
    {"id": "TANJORE", "name": "Thanjavur Delta Station", "basin": "Cauvery", "type": "gauge", "lat": 10.79, "lon": 79.13, "elevation": 57.0, "capacity_mcft": 0.0, "danger_level": 5.0},
    
    # --- BHAVANI TRIBUTARY ---
    {"id": "BHAVANISAGAR", "name": "Bhavanisagar Dam", "basin": "Bhavani", "type": "reservoir", "lat": 11.47, "lon": 77.13, "elevation": 280.0, "capacity_mcft": 32800.0, "danger_level": 105.0},
    {"id": "GOBICHETTIPALAYAM", "name": "Gobichettipalayam Gauge", "basin": "Bhavani", "type": "gauge", "lat": 11.45, "lon": 77.43, "elevation": 180.0, "capacity_mcft": 0.0, "danger_level": 6.5},
    {"id": "BHAVANI_TOWN", "name": "Bhavani Town Confluence", "basin": "Bhavani", "type": "gauge", "lat": 11.43, "lon": 77.68, "elevation": 165.0, "capacity_mcft": 0.0, "danger_level": 9.0},
    
    # --- AMARAVATHI TRIBUTARY ---
    {"id": "AMARAVATHI_DAM", "name": "Amaravathi Dam", "basin": "Amaravathi", "type": "reservoir", "lat": 10.42, "lon": 77.26, "elevation": 340.0, "capacity_mcft": 4000.0, "danger_level": 90.0},
    {"id": "UDUMALPET", "name": "Udumalpet Town Gauge", "basin": "Amaravathi", "type": "gauge", "lat": 10.58, "lon": 77.25, "elevation": 310.0, "capacity_mcft": 0.0, "danger_level": 6.0},
    {"id": "KARUR_AMARAVATHI", "name": "Karur Amaravathi Gauge", "basin": "Amaravathi", "type": "gauge", "lat": 10.98, "lon": 78.07, "elevation": 125.0, "capacity_mcft": 0.0, "danger_level": 8.0},

    # --- VAIGAI BASIN ---
    {"id": "VAIGAI_DAM", "name": "Vaigai Dam", "basin": "Vaigai", "type": "reservoir", "lat": 10.05, "lon": 77.56, "elevation": 260.0, "capacity_mcft": 6100.0, "danger_level": 71.0},
    {"id": "MADURAI", "name": "Madurai City Bridge", "basin": "Vaigai", "type": "gauge", "lat": 9.93, "lon": 78.12, "elevation": 135.0, "capacity_mcft": 0.0, "danger_level": 10.0},
    {"id": "PARAMAKUDI", "name": "Paramakudi Gauge", "basin": "Vaigai", "type": "gauge", "lat": 9.55, "lon": 78.58, "elevation": 40.0, "capacity_mcft": 0.0, "danger_level": 8.0},
    {"id": "RAMANATHAPURAM", "name": "Ramanathapuram Gauge", "basin": "Vaigai", "type": "gauge", "lat": 9.37, "lon": 78.83, "elevation": 10.0, "capacity_mcft": 0.0, "danger_level": 5.0},

    # --- TAMIRABARANI BASIN ---
    {"id": "PAPANASAM", "name": "Papanasam Dam", "basin": "Tamirabarani", "type": "reservoir", "lat": 8.71, "lon": 77.30, "elevation": 240.0, "capacity_mcft": 5500.0, "danger_level": 143.0},
    {"id": "AMBASAMUDRAM", "name": "Ambasamudram Gauge", "basin": "Tamirabarani", "type": "gauge", "lat": 8.70, "lon": 77.45, "elevation": 72.0, "capacity_mcft": 0.0, "danger_level": 7.0},
    {"id": "TIRUNELVELI", "name": "Tirunelveli Bridge", "basin": "Tamirabarani", "type": "gauge", "lat": 8.73, "lon": 77.70, "elevation": 38.0, "capacity_mcft": 0.0, "danger_level": 11.5},
    {"id": "SRIVAIKUNTAM", "name": "Srivaikuntam Anicut", "basin": "Tamirabarani", "type": "gauge", "lat": 8.63, "lon": 77.92, "elevation": 15.0, "capacity_mcft": 0.0, "danger_level": 9.0},
    {"id": "THOOTHUKUDI", "name": "Thoothukudi Delta", "basin": "Tamirabarani", "type": "gauge", "lat": 8.76, "lon": 78.13, "elevation": 2.0, "capacity_mcft": 0.0, "danger_level": 4.5},

    # --- PALAR BASIN ---
    {"id": "VANIYAMBADI", "name": "Vaniyambadi Bridge", "basin": "Palar", "type": "gauge", "lat": 12.68, "lon": 78.62, "elevation": 360.0, "capacity_mcft": 0.0, "danger_level": 6.0},
    {"id": "AMBUR", "name": "Ambur Gauge", "basin": "Palar", "type": "gauge", "lat": 12.78, "lon": 78.72, "elevation": 315.0, "capacity_mcft": 0.0, "danger_level": 6.5},
    {"id": "VELLORE", "name": "Vellore Fort Gauge", "basin": "Palar", "type": "gauge", "lat": 12.92, "lon": 79.13, "elevation": 220.0, "capacity_mcft": 0.0, "danger_level": 8.5},
    {"id": "ARCOT", "name": "Arcot Bridge", "basin": "Palar", "type": "gauge", "lat": 12.90, "lon": 79.33, "elevation": 170.0, "capacity_mcft": 0.0, "danger_level": 7.0},
    {"id": "KANCHIPURAM", "name": "Kanchipuram Outflow", "basin": "Palar", "type": "gauge", "lat": 12.83, "lon": 79.70, "elevation": 88.0, "capacity_mcft": 0.0, "danger_level": 6.0}
]

# Hydrological Flow Connections: [source_id, target_id, travel_time_hours]
CONNECTIONS = [
    # Cauvery Mainstem
    ("METTUR", "ERODE", 4.0),
    ("ERODE", "KARUR", 3.0),
    ("KARUR", "TRICHY", 6.0),
    ("TRICHY", "TANJORE", 2.0),

    # Bhavani Tributary
    ("BHAVANISAGAR", "GOBICHETTIPALAYAM", 2.0),
    ("GOBICHETTIPALAYAM", "BHAVANI_TOWN", 2.0),
    ("BHAVANI_TOWN", "ERODE", 1.0), # Merges into Cauvery at Erode

    # Amaravathi Tributary
    ("AMARAVATHI_DAM", "UDUMALPET", 1.5),
    ("UDUMALPET", "KARUR_AMARAVATHI", 4.0),
    ("KARUR_AMARAVATHI", "KARUR", 1.0), # Merges into Cauvery at Karur

    # Vaigai River
    ("VAIGAI_DAM", "MADURAI", 3.0),
    ("MADURAI", "PARAMAKUDI", 6.0),
    ("PARAMAKUDI", "RAMANATHAPURAM", 4.0),

    # Tamirabarani River
    ("PAPANASAM", "AMBASAMUDRAM", 1.5),
    ("AMBASAMUDRAM", "TIRUNELVELI", 3.0),
    ("TIRUNELVELI", "SRIVAIKUNTAM", 4.0),
    ("SRIVAIKUNTAM", "THOOTHUKUDI", 2.0),

    # Palar River
    ("VANIYAMBADI", "AMBUR", 2.0),
    ("AMBUR", "VELLORE", 4.0),
    ("VELLORE", "ARCOT", 2.5),
    ("ARCOT", "KANCHIPURAM", 5.0)
]

def build_graph_topology():
    """Builds static adjacency representation."""
    node_to_idx = {station["id"]: idx for idx, station in enumerate(STATIONS)}
    
    # Static edge lists
    edge_sources = []
    edge_targets = []
    edge_travel_times = []
    
    for src, dst, t_time in CONNECTIONS:
        if src in node_to_idx and dst in node_to_idx:
            edge_sources.append(node_to_idx[src])
            edge_targets.append(node_to_idx[dst])
            edge_travel_times.append(t_time)
            
    return node_to_idx, edge_sources, edge_targets, edge_travel_times

def generate_weather_monsoon(length_steps, step_minutes=15):
    """Generates synthetic monsoon weather system (rainfall, soil moisture)."""
    np.random.seed(42)
    timestamps = [datetime(2026, 10, 1) + timedelta(minutes=i*step_minutes) for i in range(length_steps)]
    
    # Simulate overall monsoon wave
    t_hours = np.array([i * step_minutes / 60.0 for i in range(length_steps)])
    
    # 2-3 rain events (monsoon depressions) peaking at specific times
    event_1 = np.exp(-((t_hours - 200) / 48) ** 2) * 25.0  # Moderate monsoon block
    event_2 = np.exp(-((t_hours - 450) / 24) ** 2) * 65.0  # Intense cloudburst/cyclone block
    event_3 = np.exp(-((t_hours - 600) / 36) ** 2) * 15.0  # Minor rain
    
    base_monsoon = event_1 + event_2 + event_3
    
    station_data = {}
    for station in STATIONS:
        # Add spatial variation based on basin
        basin_factor = 1.2 if station["basin"] in ["Bhavani", "Tamirabarani"] else 0.8
        noise = np.random.exponential(scale=1.5, size=length_steps) * (base_monsoon > 1.0)
        station_rain = base_monsoon * basin_factor + noise
        
        # Clip to zero
        station_rain = np.clip(station_rain, 0, None)
        
        # Soil moisture (rolling integral of rainfall with evaporation decay)
        soil_moisture = np.zeros(length_steps)
        curr_sm = 0.3
        decay = 0.9995  # evaporation decay per step
        for i in range(length_steps):
            curr_sm = curr_sm * decay + (station_rain[i] / 100.0)
            curr_sm = min(max(curr_sm, 0.2), 0.95)
            soil_moisture[i] = curr_sm
            
        station_data[station["id"]] = {
            "rain": station_rain,
            "soil_moisture": soil_moisture
        }
        
    return timestamps, station_data

def simulate_routing(length_steps, step_minutes=15):
    """Simulates the river flow propagation along the graph topology."""
    timestamps, weather = generate_weather_monsoon(length_steps, step_minutes)
    steps_per_hour = 60 // step_minutes
    
    # Initialize timeseries arrays for each station
    # Fields: water_level (m), discharge (cumecs), reservoir_storage (%), reservoir_release (cumecs)
    data = {s["id"]: {
        "water_level": np.zeros(length_steps),
        "discharge": np.zeros(length_steps),
        "storage_pct": np.zeros(length_steps),
        "release": np.zeros(length_steps)
    } for s in STATIONS}

    # Per-reservoir realistic initial fill % (July 2026, SW-monsoon onset)
    # Different basins fill at different rates; Tamirabarani is perennially fuller.
    INIT_STORAGE_PCT = {
        "METTUR":        34.2,   # Cauvery mainstem
        "BHAVANISAGAR":  28.7,   # Bhavani sub-basin
        "AMARAVATHI_DAM":61.3,   # Anamalai hills catchment
        "VAIGAI_DAM":    42.8,   # Peninsula basin
        "PAPANASAM":     73.6,   # Tamirabarani (perennial)
    }

    # Per-reservoir minimum environmental / irrigation release (cumecs)
    MIN_RELEASE = {
        "METTUR":        800.0,
        "BHAVANISAGAR":   15.0,
        "AMARAVATHI_DAM":  8.0,
        "VAIGAI_DAM":     12.0,
        "PAPANASAM":      25.0,
    }

    # Per-reservoir spillway trigger (% fill)
    SPILL_THRESHOLD = {
        "METTUR":        85.0,
        "BHAVANISAGAR":  82.0,
        "AMARAVATHI_DAM":78.0,
        "VAIGAI_DAM":    76.0,
        "PAPANASAM":     80.0,
    }

    # Basins base levels
    for s in STATIONS:
        if s["type"] == "reservoir":
            init_pct = INIT_STORAGE_PCT.get(s["id"], 45.0)
            data[s["id"]]["water_level"][:] = (init_pct / 100.0) * s["danger_level"]
            data[s["id"]]["storage_pct"][:] = init_pct
        else:
            data[s["id"]]["water_level"][:] = 1.2
            data[s["id"]]["discharge"][:] = 10.0

    # Process timestep by timestep to route upstream flows to downstream nodes
    node_to_idx, edge_sources, edge_targets, edge_travel_times = build_graph_topology()
    
    # Build incoming dictionary for downstream calculations
    incoming = {s["id"]: [] for s in STATIONS}
    for src, dst, t_time in CONNECTIONS:
        incoming[dst].append((src, t_time))
        
    # We will simulate step by step
    for t in range(length_steps):
        # 1. Update upstream reservoirs & independent source gauges first
        for station in STATIONS:
            nid = station["id"]
            rain = weather[nid]["rain"][t]
            sm = weather[nid]["soil_moisture"][t]
            
            # Local runoff contribution: rainfall * soil_moisture coefficient
            local_runoff = rain * sm * 3.5 
            
            if station["type"] == "reservoir":
                # Reservoir calculations
                # Inflow is sum of incoming connections at time t minus travel time, plus local runoff
                inflow = local_runoff * 2.0
                for upstream_id, travel_time in incoming[nid]:
                    travel_steps = int(travel_time * steps_per_hour)
                    t_lookback = max(0, t - travel_steps)
                    inflow += data[upstream_id]["discharge"][t_lookback]

                # Update storage
                prev_storage = data[nid]["storage_pct"][t-1] if t > 0 else INIT_STORAGE_PCT.get(nid, 45.0)
                capacity = station["capacity_mcft"]
                # Sim reservoir dynamics: inflow adds to storage
                # 1 cumec = 0.00306 million cubic feet per 15 mins
                inflow_mcf = inflow * 0.00306 * (step_minutes / 15.0)
                new_storage_mcf = (prev_storage / 100.0) * capacity + inflow_mcf

                # Determine release policy (per-reservoir)
                new_storage_pct = (new_storage_mcf / capacity) * 100.0
                release = MIN_RELEASE.get(nid, 5.0)  # mandated minimum
                spill_thr = SPILL_THRESHOLD.get(nid, 80.0)

                if new_storage_pct > spill_thr:
                    # Emergency spillway releases
                    release += (new_storage_pct - spill_thr) * 150.0
                if new_storage_pct > 95.0:
                    # Spill matching inflow
                    release += inflow
                    new_storage_pct = 95.0

                new_storage_mcf -= release * 0.00306 * (step_minutes / 15.0)
                new_storage_pct = max(0.0, min(100.0, (new_storage_mcf / capacity) * 100.0))
                
                data[nid]["storage_pct"][t] = new_storage_pct
                data[nid]["release"][t] = release
                data[nid]["discharge"][t] = release
                data[nid]["water_level"][t] = (new_storage_pct / 100.0) * station["danger_level"]
                
            else:
                # Gauge calculations
                # Inflow is local runoff + routed upstream flows
                inflow = local_runoff
                for upstream_id, travel_time in incoming[nid]:
                    travel_steps = int(travel_time * steps_per_hour)
                    t_lookback = max(0, t - travel_steps)
                    if STATIONS[node_to_idx[upstream_id]]["type"] == "reservoir":
                        inflow += data[upstream_id]["release"][t_lookback]
                    else:
                        inflow += data[upstream_id]["discharge"][t_lookback]
                
                # Water level and discharge dynamics
                sim_discharge = inflow + 10.0 # base flow
                sim_discharge += np.random.normal(0, 0.5)
                sim_discharge = max(2.0, sim_discharge)
                
                # Convert discharge to level
                a, b = 0.25, 0.45
                sim_level = a * (sim_discharge ** b) + 0.5
                
                data[nid]["discharge"][t] = sim_discharge
                data[nid]["water_level"][t] = sim_level
                
    # Flatten everything into a single DataFrame
    records = []
    for t in range(length_steps):
        ts = timestamps[t]
        for s in STATIONS:
            nid = s["id"]
            records.append({
                "ts": ts.strftime("%Y-%m-%dT%H:%M:%S"),
                "station_id": nid,
                "rain_observed": weather[nid]["rain"][t],
                "rain_forecast_6h": weather[nid]["rain"][min(length_steps-1, t + 6 * steps_per_hour)] + np.random.normal(0, 0.5),
                "rain_forecast_24h": weather[nid]["rain"][min(length_steps-1, t + 24 * steps_per_hour)] + np.random.normal(0, 2.0),
                "rain_forecast_72h": weather[nid]["rain"][min(length_steps-1, t + 72 * steps_per_hour)] + np.random.normal(0, 5.0),
                "soil_moisture": weather[nid]["soil_moisture"][t],
                "water_level": data[nid]["water_level"][t],
                "discharge": data[nid]["discharge"][t],
                "storage_pct": data[nid]["storage_pct"][t],
                "release": data[nid]["release"][t],
                "temperature": 25.0 + 5.0 * math.sin(t * step_minutes / 1440.0 * 2 * math.pi) + np.random.normal(0, 0.5),
                "humidity": 80.0 - 15.0 * math.sin(t * step_minutes / 1440.0 * 2 * math.pi) + np.random.normal(0, 1.0)
            })
            
    df = pd.DataFrame(records)
    # Ensure forecast values are non-negative
    for col in ["rain_forecast_6h", "rain_forecast_24h", "rain_forecast_72h"]:
        df[col] = df[col].clip(0, None)
        
    return df

def generate_and_save_data(out_dir="datasets/processed"):
    os.makedirs(out_dir, exist_ok=True)
    
    # 30 days of simulation at 15 min resolution
    length_steps = 30 * 96 
    print(f"Generating synthetic hydrology simulation data for {length_steps} timesteps...")
    
    df = simulate_routing(length_steps, step_minutes=15)
    
    # Save timeseries dataset
    data_path = os.path.join(out_dir, "flood_data.csv")
    df.to_csv(data_path, index=False)
    print(f"Saved dataset to {data_path}")
    
    # Save static graph structure
    node_to_idx, edge_sources, edge_targets, edge_travel_times = build_graph_topology()
    graph_info = {
        "stations": STATIONS,
        "connections": CONNECTIONS,
        "node_to_idx": node_to_idx,
        "edge_index": [edge_sources, edge_targets],
        "edge_travel_times": edge_travel_times
    }
    
    graph_path = os.path.join(out_dir, "graph_topology.json")
    with open(graph_path, "w") as f:
        json.dump(graph_info, f, indent=2)
    print(f"Saved graph topology to {graph_path}")

if __name__ == "__main__":
    # Correct relative path resolve if running from other dir
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(script_dir, "processed")
    generate_and_save_data(out_dir)
