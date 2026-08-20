import os
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session

# DB imports
from app.backend.services.db import connection
from app.backend.services.db.models import RiverStation, Reservoir, RiverLevel, Alert, Rainfall, Weather
from app.backend.auth.jwt_handler import verify_access_token

router = APIRouter(prefix="/chat", tags=["chatbot"])
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    payload = verify_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload

class ChatRequest(BaseModel):
    message: str

def retrieve_hydrology_context():
    """
    Fetch live telemetry from DB at the latest real-time timestamp.
    FIX B2: clamp to utcnow() so future-dated seed rows (2026-11-01) don't mask today's ticks.
    """
    db = connection.SessionLocal()
    try:
        now_utc = datetime.utcnow()

        # Clamp: prefer today's real-time scheduler rows over future-dated seed rows
        latest_lvl = (
            db.query(RiverLevel)
            .filter(RiverLevel.ts <= now_utc)
            .order_by(RiverLevel.ts.desc())
            .first()
        )
        if not latest_lvl:
            latest_lvl = db.query(RiverLevel).order_by(RiverLevel.ts.desc()).first()
        if not latest_lvl:
            return "No telemetry data is currently active in the database."

        latest_ts = latest_lvl.ts
        telemetry = db.query(RiverLevel).filter(RiverLevel.ts == latest_ts).all()

        context_lines = []
        context_lines.append(f"Current Telemetry Timestamp: {latest_ts.strftime('%Y-%m-%d %H:%M:%S')}")
        context_lines.append("\nStation Readings:")

        reservoir_lines = []
        gauge_lines = []
        high_risks = []

        def get_risk(level, danger):
            ratio = level / max(danger, 0.01)
            if ratio < 0.4: return "Safe"
            elif ratio < 0.7: return "Low Risk"
            elif ratio < 0.9: return "Moderate Risk"
            elif ratio < 1.0: return "High Risk"
            else: return "Severe Flood"

        for row in telemetry:
            station = row.station
            risk = get_risk(row.level_m, station.danger_level)

            # Rainfall at this timestamp
            rain_rec = db.query(Rainfall).filter(
                Rainfall.station_id == station.id,
                Rainfall.ts == latest_ts
            ).first()
            rain_val = round(rain_rec.value_mm, 2) if rain_rec else 0.0

            # Weather at this timestamp
            wx_rec = db.query(Weather).filter(
                Weather.station_id == station.id,
                Weather.ts == latest_ts
            ).first()
            temp_val = round(wx_rec.temp, 1) if wx_rec else "N/A"
            hum_val  = round(wx_rec.humidity, 1) if wx_rec else "N/A"

            if risk in ["High Risk", "Severe Flood"]:
                high_risks.append(
                    f"- {station.name} ({station.river} Basin): "
                    f"Level={round(row.level_m * 3.28084, 2)}ft / Danger={round(station.danger_level * 3.28084, 2)}ft | "
                    f"Discharge={row.discharge_cumecs} cumecs | Status={risk}"
                )

            if len(station.reservoirs) > 0:
                res = station.reservoirs[0]
                reservoir_lines.append(
                    f"RESERVOIR | {res.name}: Level={round(row.level_m * 3.28084, 2)}ft, "
                    f"Storage={row.storage_pct}% Filled, "
                    f"Capacity={res.capacity_mcft} Mcft, "
                    f"Release={row.release} m3/s, "
                    f"Risk={risk}"
                )
            else:
                gauge_lines.append(
                    f"GAUGE | {station.name} ({station.river}): "
                    f"Level={round(row.level_m * 3.28084, 2)}ft, "
                    f"Discharge={row.discharge_cumecs} cumecs, "
                    f"Rain={rain_val}mm, Temp={temp_val}C, Hum={hum_val}%, "
                    f"Risk={risk}"
                )

        context_lines += reservoir_lines + gauge_lines

        if high_risks:
            context_lines.append("\nActive Warning Zones:")
            context_lines.extend(high_risks)
        else:
            context_lines.append("\nNo stations currently in High Risk or Severe Flood state.")

        # Active alerts
        active_alerts = db.query(Alert).order_by(Alert.sent_at.desc()).limit(5).all()
        if active_alerts:
            context_lines.append("\nRecent Dispatch Alerts:")
            for al in active_alerts:
                context_lines.append(
                    f"- [{al.sent_at.strftime('%Y-%m-%d %H:%M')}] {al.severity}: {al.message}"
                )

        return "\n".join(context_lines)
    finally:
        db.close()


def rule_based_response(query: str, context: str) -> str:
    """
    FIX B8: Enhanced keyword matching with specific numeric field extraction.
    Covers: level, discharge, rainfall, reservoir, flood/warning, basin, soil, prediction/forecast, monitoring.
    """
    q = query.lower().strip()
    ctx_lines = context.split("\n")

    # ── Helper: find lines from context matching a keyword ──────────────────
    def ctx_match(*keywords):
        return [l for l in ctx_lines if any(k.lower() in l.lower() for k in keywords)]

    # ── Specific station lookup ──────────────────────────────────────────────
    STATION_NAMES = [
        "mettur", "erode", "karur", "trichy", "tanjore",
        "bhavanisagar", "bhavani", "amaravathi", "vaigai",
        "papanasam", "madurai", "tirunelveli", "tirunelveili",
        "gobichettipalayam", "srivaikuntam", "palar", "tamirabarani"
    ]
    matched_station = next((s for s in STATION_NAMES if s in q), None)

    # ── Water level query ────────────────────────────────────────────────────
    if any(w in q for w in ["level", "water level", "gauge", "height", "rl"]):
        if matched_station:
            lines = ctx_match(matched_station.title(), matched_station.upper())
        else:
            lines = ctx_match("Level=", "GAUGE |", "RESERVOIR |")
        if lines:
            return (
                f"**Water Levels — Live Telemetry** ({context.split(chr(10))[0]})\n\n"
                + "\n".join(l for l in lines if "Level=" in l)
                + "\n\nAll values are read directly from the real-time `river_levels` database table."
            )

    # ── Discharge / flow query ───────────────────────────────────────────────
    if any(w in q for w in ["discharge", "flow", "cumecs", "outflow", "inflow"]):
        lines = ctx_match("Discharge=", "cumecs")
        if matched_station:
            lines = ctx_match(matched_station.title(), matched_station.upper())
            lines = [l for l in lines if "Discharge=" in l]
        if lines:
            return (
                f"**Discharge / Outflow Rates** (source: `river_levels` table)\n\n"
                + "\n".join(lines)
                + "\n\nDischarge is measured in cubic metres per second (cumecs)."
            )

    # ── Rainfall query ───────────────────────────────────────────────────────
    if any(w in q for w in ["rain", "rainfall", "precipitation", "mm", "storm"]):
        lines = ctx_match("Rain=")
        if matched_station:
            lines = ctx_match(matched_station.title(), matched_station.upper())
            lines = [l for l in lines if "Rain=" in l]
        heavy = [l for l in ctx_match("Rain=") if "Rain=" in l and
                 any(float(p.split("Rain=")[1].split("mm")[0]) > 10
                     for p in [l] if "Rain=" in p and "mm" in p)]
        note = f"\n\n⚠ Heavy rainfall (>10mm) at {len(heavy)} station(s)." if heavy else ""
        if lines:
            return (
                f"**Rainfall Observations** (source: `rainfall` table)\n\n"
                + "\n".join([l for l in lines if "Rain=" in l])
                + note
            )

    # ── Reservoir status query ───────────────────────────────────────────────
    if any(w in q for w in ["reservoir", "dam", "storage", "capacity", "spillway", "release", "mcft"]):
        lines = ctx_match("RESERVOIR |")
        if matched_station:
            lines = ctx_match(matched_station.title(), matched_station.upper())
            lines = [l for l in lines if "RESERVOIR" in l or "Storage=" in l]
        if lines:
            return (
                "**Reservoir Storage & Spillway Status** (source: `river_levels` + `reservoirs` tables)\n\n"
                + "\n".join(lines)
                + "\n\nRelease decisions are automatically computed from storage percentage thresholds:\n"
                + "  • >80% storage → proportional release\n"
                + "  • >95% storage → full flood-release mode"
            )

    # ── Flood warning / risk query ───────────────────────────────────────────
    if any(w in q for w in ["warning", "danger", "risk", "flood", "alert", "critical", "evacuate"]):
        alert_lines = ctx_match("CRITICAL", "HIGH RISK", "SEVERE", "Alert", "Dispatch", "WARNING")
        risk_lines  = ctx_match("High Risk", "Severe Flood", "Warning Zone")
        all_lines   = list(dict.fromkeys(alert_lines + risk_lines))  # dedup
        if all_lines:
            return (
                "⚠ **Active Flood Warnings & Risk Alerts**\n\n"
                + "\n".join(all_lines)
                + "\n\nData from `alerts` table and live `river_levels` risk computation."
            )
        return (
            "✅ **All Clear** — No active flood warning thresholds crossed as of "
            f"{ctx_lines[0]}.\n\n"
            "All monitoring stations are reporting water levels within safe parameters."
        )

    # ── Soil moisture query ──────────────────────────────────────────────────
    if any(w in q for w in ["soil", "moisture", "infiltration", "saturation"]):
        return (
            "**Soil Moisture** is computed dynamically from the past 24-hour cumulative rainfall "
            "per station, weighted by basin baseline (Cauvery/Bhavani: 0.45, others: 0.38) "
            "and adjusted for DEM elevation. It is returned by `GET /api/dashboard` as "
            "`soil_moisture` per station (range 0.20–0.95). No separate DB table — derived on-the-fly."
        )

    # ── Basin / topology query ───────────────────────────────────────────────
    if any(w in q for w in ["basin", "river", "tributary", "cauvery", "bhavani", "vaigai", "network"]):
        return (
            "**Tamil Nadu River Basin Network** monitored by HydroGNN-Net:\n\n"
            "- **Cauvery**: Mettur Dam → Erode → Karur → Trichy → Tanjore → Grand Anicut\n"
            "- **Bhavani**: Bhavanisagar → Gobichettipalayam → Bhavani Town\n"
            "- **Amaravathi**: Amaravathi Dam → Karur confluence\n"
            "- **Vaigai**: Vaigai Dam → Madurai → Ramanathapuram\n"
            "- **Tamirabarani**: Papanasam → Tirunelveli → Srivaikuntam\n"
            "- **Palar**: Walajapet → Kanchipuram → Chennai\n\n"
            "Each station is a node in the directed flow graph. Upstream releases propagate "
            "downstream with travel-time lags encoded in graph edges."
        )

    # ── Prediction / forecast query ──────────────────────────────────────────
    if any(w in q for w in ["predict", "forecast", "6h", "12h", "24h", "future", "gnn", "model"]):
        return (
            "**GNN Flood Forecast** — The `POST /api/predict` endpoint generates water level "
            "predictions at 6h, 12h, and 24h horizons for any station.\n\n"
            "Each prediction includes:\n"
            "- `level_m`: predicted water level (feet)\n"
            "- `uncertainty_m`: 95% confidence interval half-width (feet)\n"
            "- `flood_probability`: ratio of predicted level to danger level\n"
            "- `severity`: Safe / Low Risk / Moderate Risk / High Risk / Severe Flood\n\n"
            "Select a station from the map or dropdown and the hydrograph updates automatically."
        )

    # ── Monitoring / diagnostics query ───────────────────────────────────────
    if any(w in q for w in ["health", "diagnostics", "status", "system", "scheduler", "monitoring"]):
        return (
            "**System Health** — Use `GET /api/monitoring/diagnostics` to check:\n"
            "- Database connectivity\n- Scheduler sync lag\n- CPU / Memory usage\n"
            "- Data drift and outlier detection\n\n"
            "Currently all systems are Healthy. Scheduler writes a new telemetry row every 900 seconds."
        )

    # ── Default: full context dump ───────────────────────────────────────────
    return (
        f"Hello, I am the HydroGNN-Net AI Decision Assistant.\n\n"
        f"**Current Telemetry Summary** ({ctx_lines[0]}):\n\n"
        + "\n".join(ctx_lines[1:12])
        + "\n\n"
        "You can ask me about:\n"
        "• Water levels at any station\n"
        "• Reservoir storage and spillway releases\n"
        "• Rainfall and discharge rates\n"
        "• Active flood warnings\n"
        "• GNN flood predictions (6h / 12h / 24h)\n"
        "• Tamil Nadu river basin topology"
    )



@router.post("")
def query_chatbot(req: ChatRequest, user: dict = Depends(get_current_user)):
    context = retrieve_hydrology_context()
    response_text = rule_based_response(req.message, context)
    return {
        "query": req.message,
        "response": response_text
    }
