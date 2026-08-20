import os
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime
import numpy as np
from sqlalchemy.orm import Session
from app.backend.services.db.models import Weather, Rainfall, RiverStation
from app.backend.services.logging_manager import api_logger

def fetch_and_store_weather(db: Session, ts: datetime):
    print(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] Ingesting weather & rainfall from live APIs...")
    stations = db.query(RiverStation).all()
    api_key = os.getenv("OPENWEATHER_API_KEY", "").strip()

    if not api_key:
        api_logger.warning(
            "OPENWEATHER_API_KEY is not set in .env — OpenWeather is DISABLED. "
            "Add your free key at https://home.openweathermap.org/api_keys "
            "then set OPENWEATHER_API_KEY=<key> in .env and restart the server."
        )

    ow_ok = 0    # stations successfully fetched from OpenWeather
    nasa_ok = 0  # stations fetched from NASA POWER
    sim_ok = 0   # stations falling back to simulation

    for station in stations:
        rain_val = 0.0
        temp_val = 27.0
        humidity_val = 80.0
        wind_speed = 4.5
        pressure_hpa = 1010.0
        source = "simulation"
        success = False

        # 1. Primary: Try OpenWeather if API key is present
        if api_key:
            url = (
                f"https://api.openweathermap.org/data/2.5/weather"
                f"?lat={station.lat}&lon={station.lon}&appid={api_key}&units=metric"
            )
            t0 = time.time()
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=8) as res:
                    ms = round((time.time() - t0) * 1000)
                    data = json.loads(res.read().decode("utf-8"))
                    temp_val      = float(data["main"]["temp"])
                    humidity_val  = float(data["main"]["humidity"])
                    wind_speed    = float(data["wind"]["speed"])
                    pressure_hpa  = float(data["main"].get("pressure", 1010.0))
                    if "rain" in data:
                        rain_val = float(data["rain"].get("1h", data["rain"].get("3h", 0.0)))
                    source = "openweather"
                    success = True
                    ow_ok += 1
                    api_logger.info(
                        f"[OpenWeather] {station.name}: HTTP 200 in {ms}ms | "
                        f"temp={temp_val}C hum={humidity_val}% wind={wind_speed}m/s "
                        f"pressure={pressure_hpa}hPa rain={rain_val}mm"
                    )
            except urllib.error.HTTPError as e:
                body = e.read().decode()
                api_logger.warning(
                    f"[OpenWeather] {station.name}: HTTP {e.code} error: {body[:120]}. "
                    "Falling back to NASA POWER."
                )
            except Exception as e:
                api_logger.warning(
                    f"[OpenWeather] {station.name}: {e}. Falling back to NASA POWER."
                )

        # 2. Secondary: Fall back to free, public NASA POWER API (no credentials required)
        if not success:
            t0 = time.time()
            try:
                date_str = ts.strftime("%Y%m%d")
                url = (
                    f"https://power.larc.nasa.gov/api/temporal/daily/point"
                    f"?parameters=PRECTOTCORR,T2M,RH2M&community=AG"
                    f"&longitude={station.lon}&latitude={station.lat}"
                    f"&start={date_str}&end={date_str}&format=JSON"
                )
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=8) as res:
                    ms = round((time.time() - t0) * 1000)
                    data = json.loads(res.read().decode("utf-8"))
                    props = data.get("properties", {}).get("parameter", {})
                    rain_dict = props.get("PRECTOTCORR", {})
                    temp_dict = props.get("T2M", {})
                    hum_dict  = props.get("RH2M", {})
                    if rain_dict:
                        k        = list(rain_dict.keys())[0]
                        rain_raw = float(rain_dict[k])
                        temp_raw = float(temp_dict[k])
                        hum_raw  = float(hum_dict[k])
                        if rain_raw > -990 and temp_raw > -990 and hum_raw > -990:
                            rain_val     = max(0.0, rain_raw)
                            temp_val     = temp_raw
                            humidity_val = hum_raw
                            source       = "nasa_power"
                            success      = True
                            nasa_ok     += 1
                            api_logger.info(
                                f"[NASA POWER] {station.name}: HTTP 200 in {ms}ms | "
                                f"temp={temp_val}C hum={humidity_val}% rain={rain_val}mm"
                            )
                        else:
                            api_logger.warning(
                                f"[NASA POWER] {station.name}: fill value (-999) returned "
                                f"in {ms}ms. Falling back to simulation."
                            )
            except Exception as e:
                api_logger.warning(f"[NASA POWER] {station.name}: {e}. Falling back to simulation.")

        # 3. Fallback to physical simulation values if both API calls failed
        if not success:
            day_of_year = ts.timetuple().tm_yday
            t_hours = day_of_year * 24.0 + ts.hour
            event_sw = np.exp(-((day_of_year - 170) / 20.0) ** 2) * 30.0
            event_ne = np.exp(-((day_of_year - 290) / 25.0) ** 2) * 55.0
            base_monsoon = max(0.0, event_sw + event_ne)
            basin_factor = 1.2 if station.river in ["Bhavani", "Tamirabarani"] else 0.8
            np.random.seed(abs(station.lat.__hash__() % 1000 + int(t_hours)) % (2**32))
            noise = np.random.exponential(scale=1.5) * (base_monsoon > 1.0)
            rain_val = float(max(0.0, base_monsoon * basin_factor + noise))
            temp_val = float(25.0 + 5.0 * np.sin(t_hours / 24.0 * 2 * np.pi) + np.random.normal(0, 0.5))
            humidity_val = float(max(40.0, min(100.0, 80.0 - 15.0 * np.sin(t_hours / 24.0 * 2 * np.pi) + np.random.normal(0, 1.0))))
            wind_speed = float(max(1.0, 3.5 + np.random.normal(0, 0.8)))
            source = "simulation"
            sim_ok += 1
            api_logger.debug(f"[Simulation] {station.name}: temp={round(temp_val,1)}C rain={round(rain_val,2)}mm")

        # Write Weather record
        weather_rec = Weather(
            station_id=station.id,
            ts=ts,
            temp=round(temp_val, 1),
            humidity=round(humidity_val, 1),
            wind_speed=round(wind_speed, 1),
            source=source  # Issue #4 fix: propagate source label
        )
        db.add(weather_rec)

        # Write Rainfall record
        rainfall_rec = Rainfall(
            station_id=station.id,
            ts=ts,
            value_mm=round(rain_val, 2),
            source=source
        )
        db.add(rainfall_rec)

    db.commit()
    total = ow_ok + nasa_ok + sim_ok
    print(
        f"  Ingested weather & rainfall for {total} stations: "
        f"openweather={ow_ok}  nasa_power={nasa_ok}  simulation={sim_ok}"
    )
    if sim_ok > 0 and not api_key:
        print(
            "  [!] OpenWeather key not set -- add OPENWEATHER_API_KEY to .env "
            "to use live weather as primary source."
        )
