import os
import json
import asyncio
import traceback
from datetime import datetime, timedelta
import torch
import numpy as np
from sqlalchemy.orm import Session

# DB models
from app.backend.services.db import connection
from app.backend.services.db.models import RiverLevel, Prediction, Alert, RiverStation, Rainfall, Weather

# Ingestions
from app.backend.services.ingestion.weather_api import fetch_and_store_weather
from app.backend.services.ingestion.cwc_scraper import fetch_and_store_hydrology
from app.backend.services.ingestion.satellite_api import fetch_and_store_satellite

# Model resources
from models.routing_model import HydroGNNNet

# Global reference to scheduler task
SCHEDULER_RUNNING = False
TICK_LOCK = False

async def start_realtime_scheduler():
    global SCHEDULER_RUNNING
    if SCHEDULER_RUNNING:
        return

    SCHEDULER_RUNNING = True
    asyncio.create_task(scheduler_loop())
    print("Real-time scheduler daemon task started successfully.")

async def execute_scheduler_tick():
    global TICK_LOCK
    if TICK_LOCK:
        print("  [Scheduler Skip] Previous tick still running. Skipping to avoid queue stacking.")
        return

    TICK_LOCK = True
    try:
        real_ts = datetime.utcnow().replace(second=0, microsecond=0)
        minute_floor = (real_ts.minute // 15) * 15
        real_ts = real_ts.replace(minute=minute_floor)

        print(f"\n[{real_ts.strftime('%Y-%m-%d %H:%M:%S')} UTC] Executing live ingestion tick...")

        def run_w():
            db = connection.SessionLocal()
            try:
                fetch_and_store_weather(db, real_ts)
            finally:
                db.close()

        def run_h():
            db = connection.SessionLocal()
            try:
                fetch_and_store_hydrology(db, real_ts)
            finally:
                db.close()

        def run_s():
            db = connection.SessionLocal()
            try:
                fetch_and_store_satellite(db, real_ts)
            finally:
                db.close()

        def run_p():
            db = connection.SessionLocal()
            try:
                run_realtime_predictions(db, real_ts)
            finally:
                db.close()

        def run_a():
            db = connection.SessionLocal()
            try:
                evaluate_realtime_alerts(db, real_ts)
            finally:
                db.close()

        await asyncio.to_thread(run_w)
        await asyncio.to_thread(run_h)
        await asyncio.to_thread(run_s)
        await asyncio.to_thread(run_p)
        await asyncio.to_thread(run_a)

    except Exception as outer_e:
        print(f"Outer scheduler loop error: {str(outer_e)}")
    finally:
        TICK_LOCK = False

async def scheduler_loop():
    interval = int(os.getenv("SCHEDULER_INTERVAL_SEC", "900"))  # 15-minute real-time cadence
    print(f"Scheduler daemon active. Sleep interval: {interval} seconds.")

    # Execute immediate initial tick on backend startup
    await execute_scheduler_tick()

    while SCHEDULER_RUNNING:
        await asyncio.sleep(interval)
        await execute_scheduler_tick()

def run_realtime_predictions(db: Session, current_ts: datetime):
    # Load model and config paths
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    project_dir = os.path.dirname(os.path.dirname(backend_dir))

    checkpoint_dir = os.path.join(project_dir, "training", "checkpoints")
    stats_path = os.path.join(checkpoint_dir, "scaling_stats.json")
    model_path  = os.path.join(checkpoint_dir, "best_model.pt")

    if not os.path.exists(stats_path) or not os.path.exists(model_path):
        print("  [Prediction Skip] GNN weights not trained yet. Skipping forecasting step.")
        return

    with open(stats_path, "r") as f:
        scaling_stats = json.load(f)

    stations = db.query(RiverStation).all()
    num_nodes = len(stations)
    node_to_idx = {s.id: idx for idx, s in enumerate(stations)}

    # Verify we have at least 24 historical timesteps for lookback window
    latest_levels_count = db.query(RiverLevel).filter(
        RiverLevel.ts <= current_ts
    ).order_by(RiverLevel.ts.desc()).count()
    if latest_levels_count < 24 * num_nodes:
        print("  [Prediction Skip] Insufficient telemetry history. Need at least 24 hours of data.")
        return

    # Get last 24 records per station
    levels_data = db.query(RiverLevel).filter(
        RiverLevel.ts <= current_ts
    ).order_by(RiverLevel.ts.desc()).limit(24 * num_nodes).all()
    levels_data.reverse()

    # Construct historical tensor: [1, 24, N, 8]
    hist_x   = np.zeros((1, 24, num_nodes, 8))
    max_elev = max(s.dem_elevation for s in stations)

    def norm(col, val):
        mean = scaling_stats["means"][col]
        std  = scaling_stats["stds"][col]
        return (val - mean) / std

    for step_i in range(24):
        step_records = levels_data[step_i * num_nodes : (step_i + 1) * num_nodes]
        for row in step_records:
            idx     = node_to_idx[row.station_id]
            station = row.station

            rain_rec = db.query(Rainfall).filter(
                Rainfall.station_id == row.station_id, Rainfall.ts == row.ts
            ).first()
            rain = rain_rec.value_mm if rain_rec else 0.0

            weather_rec = db.query(Weather).filter(
                Weather.station_id == row.station_id, Weather.ts == row.ts
            ).first()
            temp     = weather_rec.temp     if weather_rec else 27.0
            humidity = weather_rec.humidity if weather_rec else 80.0

            sm = min(0.95, max(0.2, 0.3 + rain / 50.0))

            hist_x[0, step_i, idx, 0] = norm("rain_observed",  rain)
            hist_x[0, step_i, idx, 1] = sm
            hist_x[0, step_i, idx, 2] = norm("temperature",    temp)
            hist_x[0, step_i, idx, 3] = norm("humidity",       humidity)
            hist_x[0, step_i, idx, 4] = station.dem_elevation / max_elev
            hist_x[0, step_i, idx, 5] = 1.0 if len(station.reservoirs) > 0 else 0.0
            hist_x[0, step_i, idx, 6] = norm("water_level",   row.level_m)
            hist_x[0, step_i, idx, 7] = norm("discharge",      row.discharge_cumecs)

    # Neutral weather forecast (96 steps = 24 hours at 15-min cadence)
    fut_w = np.zeros((1, 96, num_nodes, 3))
    for idx in range(num_nodes):
        fut_w[0, :, idx, 0] = norm("rain_forecast_6h",  0.1)
        fut_w[0, :, idx, 1] = norm("rain_forecast_24h", 0.5)
        fut_w[0, :, idx, 2] = norm("rain_forecast_72h", 1.5)

    hist_x_t = torch.tensor(hist_x, dtype=torch.float32)
    fut_w_t  = torch.tensor(fut_w,  dtype=torch.float32)

    # Load dynamic graph structure
    from app.backend.services.routing.multiscale_graph import build_dynamic_multiscale_graph
    full_edge_index, full_edge_lags, _ = build_dynamic_multiscale_graph(db, current_ts)

    physical_edges, physical_lags = [], []
    for i in range(full_edge_index.shape[1]):
        u, v = full_edge_index[0, i].item(), full_edge_index[1, i].item()
        if u < 25 and v < 25:
            physical_edges.append([u, v])
            physical_lags.append(full_edge_lags[i].item())

    edge_index        = torch.tensor(physical_edges, dtype=torch.long).t().contiguous()
    edge_travel_times = torch.tensor(physical_lags,  dtype=torch.float32)

    model = HydroGNNNet(
        node_in_dim=8, weather_in_dim=3, hidden_dim=64, heads=4, num_layers=2, dropout=0.1
    )
    model.load_state_dict(torch.load(model_path, map_location="cpu"), strict=False)
    model.eval()

    mean_lvl, std_lvl, mean_q, std_q, mean_sev, mean_arr, std_arr = model.predict_with_uncertainty(
        hist_x_t, fut_w_t, edge_index, edge_travel_times, num_samples=10
    )

    mean_lvl  = mean_lvl[0].numpy()
    std_lvl   = std_lvl[0].numpy()
    mean_sev  = mean_sev[0].numpy()
    mean_arr  = mean_arr[0].numpy()

    mean_y_val = scaling_stats["means"]["water_level"]
    std_y_val  = scaling_stats["stds"]["water_level"]
    mean_lvl_denorm = mean_lvl * std_y_val + mean_y_val
    std_lvl_denorm  = std_lvl  * std_y_val

    severity_labels = ["Safe", "Low Risk", "Moderate Risk", "High Risk", "Severe Flood"]

    horizons            = {6: 23,  12: 47, 24: 95}
    extrapolate_horizons = {48: 95, 72: 95}

    for station_i, s in enumerate(stations):
        for h, step_idx in horizons.items():
            lvl_val  = float(mean_lvl_denorm[step_idx, station_i])
            std_val  = float(std_lvl_denorm[step_idx, station_i])
            sev_probs     = mean_sev[step_idx, station_i]
            best_sev_idx  = int(np.argmax(sev_probs))
            flood_prob    = float(np.sum(sev_probs[3:]))
            arr_val       = float(mean_arr[step_idx, station_i])

            pred = Prediction(
                station_id=s.id,
                issued_at=current_ts,
                horizon_hours=h,
                predicted_level=round(lvl_val, 2),
                uncertainty=round(std_val, 2),
                flood_probability=round(flood_prob, 2),
                severity_class=severity_labels[best_sev_idx],
                confidence=round(float(sev_probs[best_sev_idx]), 2),
                arrival_time_hours=round(max(0.0, arr_val), 1)
            )
            db.add(pred)

        for h, step_idx in extrapolate_horizons.items():
            decay_factor = 0.98 if h == 48 else 0.95
            lvl_val = float(mean_lvl_denorm[step_idx, station_i]) * decay_factor
            std_val = float(std_lvl_denorm[step_idx, station_i])  * (1.5 if h == 48 else 2.0)

            pred = Prediction(
                station_id=s.id,
                issued_at=current_ts,
                horizon_hours=h,
                predicted_level=round(lvl_val, 2),
                uncertainty=round(std_val, 2),
                flood_probability=0.2,
                severity_class="Safe",
                confidence=0.6,
                arrival_time_hours=0.0
            )
            db.add(pred)

    db.commit()
    print("  Calculated and stored multi-horizon real-time predictions.")

def evaluate_realtime_alerts(db: Session, ts: datetime):
    predictions = db.query(Prediction).filter(Prediction.issued_at == ts).all()

    for pred in predictions:
        if pred.severity_class in ["High Risk", "Severe Flood"] and pred.horizon_hours == 24:
            two_hours_ago = ts - timedelta(hours=2)
            recent_alert  = db.query(Alert).filter(
                Alert.station_id == pred.station_id,
                Alert.sent_at >= two_hours_ago
            ).first()

            if not recent_alert:
                station = pred.station
                lvl_ft = round(pred.predicted_level * 3.28084, 2)
                danger_ft = round(station.danger_level * 3.28084, 2)
                msg = (
                    f"FLOOD ALERT: {station.name} ({station.river} Basin) is predicted to reach "
                    f"{lvl_ft}ft in 24 hours (Danger: {danger_ft}ft). "
                    f"Severity: {pred.severity_class}. Actions: Evacuate low-lying areas."
                )
                alert = Alert(
                    id=f"ALERT_{pred.station_id}_{ts.strftime('%Y%m%d%H%M')}",
                    station_id=pred.station_id,
                    prediction_id=pred.id,
                    sent_at=ts,
                    channel="dashboard,email",
                    message=msg,
                    severity="CRITICAL" if pred.severity_class == "Severe Flood" else "WARNING"
                )
                db.add(alert)
                print(f"  [ALERT TRIGGER] Sent alert for {station.name} to control room.")

    db.commit()
