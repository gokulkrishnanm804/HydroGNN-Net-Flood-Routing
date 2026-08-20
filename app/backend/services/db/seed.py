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
        
    # 3. Seed 24 hours of telemetry history leading to 2026-11-01 00:00:00
    from datetime import datetime, timedelta
    from app.backend.services.db.models import RiverLevel, Rainfall, Weather
    start_ts = datetime(2026, 10, 31, 0, 0, 0)
    end_ts = datetime(2026, 11, 1, 0, 0, 0)
    
    levels_exist = db.query(RiverLevel).first()
    if not levels_exist:
        print("Seeding initial 24 hours of telemetry history...")
        t = start_ts
        steps = []
        while t <= end_ts:
            steps.append(t)
            t += timedelta(minutes=15)
            
        for ts in steps:
            for s in STATIONS:
                rain = 0.5 if s["id"] in ["METTUR", "BHAVANISAGAR"] else 0.1
                temp = 27.5
                humidity = 82.0
                wind = 4.0
                
                level_val = s["danger_level"] * 0.5
                discharge_val = 25.0
                storage_pct = 45.0 if s["type"] == "reservoir" else 0.0
                release = 5.0 if s["type"] == "reservoir" else 0.0
                
                weather_rec = Weather(station_id=s["id"], ts=ts, temp=temp, humidity=humidity, wind_speed=wind)
                db.add(weather_rec)
                
                rain_rec = Rainfall(station_id=s["id"], ts=ts, value_mm=rain, source="seeding")
                db.add(rain_rec)
                
                lvl_rec = RiverLevel(
                    station_id=s["id"],
                    ts=ts,
                    level_m=level_val,
                    discharge_cumecs=discharge_val,
                    storage_pct=storage_pct,
                    release=release
                )
                db.add(lvl_rec)
        db.commit()
        print("Telemetry history seeding completed.")
        
    db.commit()
    print("Database seeding completed.")

if __name__ == "__main__":
    engine = initialize_database()
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()
