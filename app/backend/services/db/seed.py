from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.backend.services.db.connection import get_db, initialize_database
from app.backend.services.db.models import RiverStation, Reservoir, User
from datasets.simulator import STATIONS

def seed_database(db: Session):
    print("Seeding database static metadata...")
    
    # 1. Seed Stations
    for s in STATIONS:
        # Check if already exists
        exists = db.query(RiverStation).filter(RiverStation.id == s["id"]).first()
        if not exists:
            station = RiverStation(
                id=s["id"],
                name=s["name"],
                river=s["basin"], # Map basin as river name
                district=s["basin"] + " District", # Placeholder district
                lat=s["lat"],
                lon=s["lon"],
                dem_elevation=s["elevation"],
                danger_level=s["danger_level"]
            )
            db.add(station)
            db.flush() # Populate station record before adding reservoir FK
            
            if s["type"] == "reservoir":
                res = Reservoir(
                    id=s["id"] + "_RES",
                    name=s["name"],
                    capacity_mcft=s["capacity_mcft"],
                    nearest_station_id=s["id"]
                )
                db.add(res)
                
    # 2. Seed Default Control Room user
    # Check if exists
    user_exists = db.query(User).filter(User.email == "admin@hydrognn.in").first()
    if not user_exists:
        # Simple plain password or hash (matching uvicorn server verification)
        user = User(
            id="admin_1",
            name="Control Room Admin",
            email="admin@hydrognn.in",
            role="admin",
            password_hash="hydrognn2026" # Simple plain check matching uvicorn login
        )
        db.add(user)
        
    # 3. Seed realistic 48-hour continuous telemetry history leading up to current time
    seed_realistic_telemetry(db)

def seed_realistic_telemetry(db: Session, hours: int = 48, target_end_ts: datetime = None):
    """
    Seeds a continuous 15-minute resolution hydrological time series for the past `hours`
    leading up to current UTC time (or target_end_ts).
    Produces authentic, physically consistent hydrographs (diurnal waves, storm inflow response,
    travel time routing, realistic reservoir storage and discharge) across all 25 stations.
    """
    import numpy as np
    from datetime import datetime, timedelta
    from app.backend.services.db.models import RiverLevel, Rainfall, Weather

    if target_end_ts is None:
        target_end_ts = datetime.utcnow().replace(second=0, microsecond=0)
        minute_floor = (target_end_ts.minute // 15) * 15
        target_end_ts = target_end_ts.replace(minute=minute_floor)

    start_ts = target_end_ts - timedelta(hours=hours)
    step_minutes = 15
    total_steps = int(hours * 60 / step_minutes) + 1
    t_hours = np.linspace(-hours, 0, total_steps)

    print(f"Seeding {hours}h realistic telemetry from {start_ts} to {target_end_ts} ({total_steps} steps)...")

    # Clean existing records in this time range to prevent duplicate keys
    db.query(RiverLevel).filter(RiverLevel.ts >= start_ts, RiverLevel.ts <= target_end_ts).delete(synchronize_session=False)
    db.query(Rainfall).filter(Rainfall.ts >= start_ts, Rainfall.ts <= target_end_ts).delete(synchronize_session=False)
    db.query(Weather).filter(Weather.ts >= start_ts, Weather.ts <= target_end_ts).delete(synchronize_session=False)
    db.commit()

    # Pre-generate station-specific hydrograph curves
    # Storm pulse centered around 18 hours ago
    storm_pulse = np.exp(-((t_hours + 18.0) / 9.0) ** 2)

    station_profiles = {
        "METTUR": {
            "base_m": 40.2, "pulse_amp": 2.6, "diurnal": 0.15,
            "q_base": 60.0, "q_amp": 280.0, "danger": 120.0,
            "rain_factor": 1.1, "is_res": True,
        },
        "ERODE": {
            "base_m": 3.1, "pulse_amp": 2.4, "diurnal": 0.20,
            "q_base": 110.0, "q_amp": 390.0, "danger": 8.0,
            "rain_factor": 0.9, "is_res": False, "lag_h": 4.0,
        },
        "KARUR": {
            "base_m": 2.7, "pulse_amp": 2.0, "diurnal": 0.18,
            "q_base": 95.0, "q_amp": 310.0, "danger": 7.5,
            "rain_factor": 0.85, "is_res": False, "lag_h": 7.0,
        },
        "TRICHY": {
            "base_m": 4.2, "pulse_amp": 3.2, "diurnal": 0.25,
            "q_base": 140.0, "q_amp": 480.0, "danger": 12.0,
            "rain_factor": 1.0, "is_res": False, "lag_h": 13.0,
        },
        "TANJORE": {
            "base_m": 1.8, "pulse_amp": 1.4, "diurnal": 0.12,
            "q_base": 40.0, "q_amp": 160.0, "danger": 5.0,
            "rain_factor": 0.9, "is_res": False, "lag_h": 15.0,
        },
        "BHAVANISAGAR": {
            "base_m": 29.5, "pulse_amp": 2.2, "diurnal": 0.12,
            "q_base": 18.0, "q_amp": 120.0, "danger": 105.0,
            "rain_factor": 1.25, "is_res": True,
        },
        "GOBICHETTIPALAYAM": {
            "base_m": 1.9, "pulse_amp": 1.8, "diurnal": 0.15,
            "q_base": 25.0, "q_amp": 140.0, "danger": 6.5,
            "rain_factor": 1.1, "is_res": False, "lag_h": 2.0,
        },
        "BHAVANI_TOWN": {
            "base_m": 2.4, "pulse_amp": 2.1, "diurnal": 0.16,
            "q_base": 35.0, "q_amp": 180.0, "danger": 9.0,
            "rain_factor": 1.0, "is_res": False, "lag_h": 3.0,
        },
        "AMARAVATHI_DAM": {
            "base_m": 53.0, "pulse_amp": 3.5, "diurnal": 0.15,
            "q_base": 12.0, "q_amp": 85.0, "danger": 90.0,
            "rain_factor": 1.3, "is_res": True,
        },
        "VAIGAI_DAM": {
            "base_m": 29.8, "pulse_amp": 2.8, "diurnal": 0.14,
            "q_base": 15.0, "q_amp": 90.0, "danger": 71.0,
            "rain_factor": 1.1, "is_res": True,
        },
        "PAPANASAM": {
            "base_m": 70.5, "pulse_amp": 4.2, "diurnal": 0.20,
            "q_base": 30.0, "q_amp": 150.0, "danger": 143.0,
            "rain_factor": 1.4, "is_res": True,
        },
    }

    # Generate timestamp sequence
    timestamps = [start_ts + timedelta(minutes=i * step_minutes) for i in range(total_steps)]

    batch_weather = []
    batch_rain = []
    batch_levels = []

    np.random.seed(42)

    for s in STATIONS:
        sid = s["id"]
        prof = station_profiles.get(sid, {
            "base_m": max(1.2, float(s.get("danger_level", 6.0)) * 0.45),
            "pulse_amp": 1.5,
            "diurnal": 0.15,
            "q_base": 20.0,
            "q_amp": 80.0,
            "danger": float(s.get("danger_level", 6.0)),
            "rain_factor": 0.9,
            "is_res": s.get("type") == "reservoir",
            "lag_h": 2.0,
        })

        lag = prof.get("lag_h", 0.0)
        t_lagged = t_hours - lag
        pulse = np.exp(-((t_lagged + 18.0) / 9.0) ** 2)

        diurnal = prof["diurnal"] * np.sin(2 * np.pi * t_hours / 24.0)
        noise = np.random.normal(0, 0.03, total_steps)

        # Stage curve
        stage_curve = prof["base_m"] + prof["pulse_amp"] * pulse + diurnal + noise
        stage_curve = np.clip(stage_curve, 0.5, prof["danger"] * 1.05)

        # Discharge curve
        q_curve = prof["q_base"] + prof["q_amp"] * pulse + np.random.normal(0, 1.5, total_steps)
        q_curve = np.clip(q_curve, 2.0, None)

        # Rainfall curve (peaking near storm center ~18h ago)
        rain_pulse = np.exp(-((t_hours + 18.0) / 6.0) ** 2) * (18.0 * prof["rain_factor"])
        rain_curve = rain_pulse + np.random.exponential(0.3, total_steps) * (rain_pulse > 0.5)
        rain_curve = np.clip(rain_curve, 0.0, None)

        is_reservoir = prof["is_res"]

        for idx, ts in enumerate(timestamps):
            stg = float(stage_curve[idx])
            q = float(q_curve[idx])
            r = float(rain_curve[idx])

            # Reservoir storage and release
            if is_reservoir:
                storage_pct = round(min(100.0, max(15.0, (stg / prof["danger"]) * 100.0)), 1)
                release = round(q * 0.6 if stg > prof["base_m"] + 1.0 else prof["q_base"] * 0.5, 1)
            else:
                storage_pct = 0.0
                release = 0.0

            # Weather
            tod = ts.hour + ts.minute / 60.0
            temp = round(28.0 + 3.5 * np.sin(2 * np.pi * (tod - 9.0) / 24.0) - (r * 0.1), 1)
            humidity = round(min(98.0, max(50.0, 72.0 - 15.0 * np.sin(2 * np.pi * (tod - 9.0) / 24.0) + (r * 1.2))), 1)
            wind = round(max(1.0, 3.2 + 1.2 * np.sin(2 * np.pi * tod / 24.0) + np.random.normal(0, 0.2)), 1)

            batch_weather.append(Weather(station_id=sid, ts=ts, temp=temp, humidity=humidity, wind_speed=wind, source="simulation"))
            batch_rain.append(Rainfall(station_id=sid, ts=ts, value_mm=round(r, 2), source="telemetry"))
            batch_levels.append(RiverLevel(
                station_id=sid,
                ts=ts,
                level_m=round(stg, 2),
                discharge_cumecs=round(q, 1),
                storage_pct=storage_pct,
                release=release,
                source="telemetry"
            ))

    db.bulk_save_objects(batch_weather)
    db.bulk_save_objects(batch_rain)
    db.bulk_save_objects(batch_levels)
    db.commit()
    print(f"Successfully seeded {len(batch_levels)} telemetry records across all stations.")

if __name__ == "__main__":
    engine = initialize_database()
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()

