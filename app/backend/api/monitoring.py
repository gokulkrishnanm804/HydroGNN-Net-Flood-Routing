import os
import sys
import time
import subprocess
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

# DB & Log imports
from app.backend.services.db.connection import get_db
from app.backend.services.db.models import RiverLevel, Prediction, ModelRegistry
from app.backend.services.logging_manager import api_logger

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

# ── Persistent CPU sample: first psutil call always returns 0.0 when
#    interval=None because it needs a baseline.  We keep a module-level
#    reference so subsequent calls return a real percentage.
try:
    import psutil as _psutil
    _psutil.cpu_percent(interval=0.1)   # prime the counter once at import time
    _PSUTIL_OK = True
except ImportError:
    _PSUTIL_OK = False


def get_system_metrics():
    cpu_percent = 0.0
    mem_percent = 0.0

    if _PSUTIL_OK:
        try:
            import psutil
            # interval=0.1 blocks briefly but guarantees a real reading
            cpu_percent = psutil.cpu_percent(interval=0.1)
            mem_percent = psutil.virtual_memory().percent
            return {
                "cpu_usage_pct": round(cpu_percent, 1),
                "memory_usage_pct": round(mem_percent, 1)
            }
        except Exception:
            pass

    # Fallback for Windows when psutil is unavailable
    try:
        if sys.platform == 'win32':
            mem_output = subprocess.check_output(
                "wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /Value",
                shell=True
            ).decode('utf-8')
            lines = [l.strip() for l in mem_output.split('\n') if '=' in l]
            stats = dict(item.split('=') for item in lines)
            free_kb = float(stats.get("FreePhysicalMemory", 0))
            total_kb = float(stats.get("TotalVisibleMemorySize", 0))
            if total_kb > 0:
                mem_percent = round((1 - (free_kb / total_kb)) * 100, 1)

            cpu_output = subprocess.check_output(
                "wmic cpu get LoadPercentage /Value",
                shell=True
            ).decode('utf-8')
            cpu_lines = [l.strip() for l in cpu_output.split('\n') if '=' in l]
            cpu_stats = dict(item.split('=') for item in cpu_lines)
            cpu_percent = float(cpu_stats.get("LoadPercentage", 0.0))
    except Exception:
        pass   # Leave as 0.0 — better to show 0 than a fake value

    return {
        "cpu_usage_pct": round(cpu_percent, 1),
        "memory_usage_pct": round(mem_percent, 1)
    }


# ── Measured inference latency (updated by /predict endpoint) ──────────────
# predict.py will call set_last_inference_latency() after each forward pass.
_last_inference_latency_ms: float = 0.0

def set_last_inference_latency(ms: float):
    global _last_inference_latency_ms
    _last_inference_latency_ms = round(ms, 2)

def get_last_inference_latency() -> float:
    return _last_inference_latency_ms


@router.get("/diagnostics")
def get_diagnostics(db: Session = Depends(get_db)):
    start_time = time.time()
    api_logger.info("Executing monitoring diagnostics check...")

    # 1. Database Health Check
    db_status = "Healthy"
    try:
        db.execute(text("SELECT 1")).scalar()
    except Exception as e:
        db_status = f"Unhealthy: {str(e)}"

    # 2. Scheduler Telemetry Sync Health
    # Clamp to utcnow() so today's scheduler rows win over future-dated seed rows.
    scheduler_status = "Healthy"
    from datetime import datetime
    now_utc = datetime.utcnow()
    latest_lvl = (
        db.query(RiverLevel)
        .filter(RiverLevel.ts <= now_utc)
        .order_by(RiverLevel.ts.desc())
        .first()
    )
    if not latest_lvl:
        latest_lvl = db.query(RiverLevel).order_by(RiverLevel.ts.desc()).first()
    if latest_lvl:
        lag_seconds = (now_utc - latest_lvl.ts).total_seconds()
        if lag_seconds > 3600 * 2:
            scheduler_status = f"Warning: No database sync updates for {round(lag_seconds / 3600, 1)} hours."
    else:
        scheduler_status = "Warning: No telemetry synced yet."

    # 3. Model & Data Drift — read from model_registry table if available.
    #    Falls back to computed outlier analysis if no registry entry exists.
    model_drift_status = "No model registered"
    try:
        registry_entry = (
            db.query(ModelRegistry)
            .filter(ModelRegistry.deployment_status == "active")
            .order_by(ModelRegistry.training_date.desc())
            .first()
        )
        if registry_entry:
            # Use the actual validation metrics stored at training time
            model_drift_status = (
                f"Active model v{registry_entry.model_version} | "
                f"Val NSE={registry_entry.val_nse:.4f} | "
                f"Val RMSE={registry_entry.val_rmse:.4f} m"
            )
        else:
            # Fall back to staged model if no active one
            staged = (
                db.query(ModelRegistry)
                .order_by(ModelRegistry.training_date.desc())
                .first()
            )
            if staged:
                model_drift_status = (
                    f"Staged model v{staged.model_version} | "
                    f"Val NSE={staged.val_nse:.4f} | "
                    f"Val RMSE={staged.val_rmse:.4f} m"
                )
    except Exception as e:
        model_drift_status = f"Registry unavailable: {str(e)[:60]}"

    # 4. Data drift: outlier ratio in most recent 100 telemetry records
    drift_status = "Stable"
    anomalies_detected = 0
    recent_levels = db.query(RiverLevel).order_by(RiverLevel.ts.desc()).limit(100).all()
    if len(recent_levels) > 10:
        for r in recent_levels:
            if r.level_m > r.station.danger_level * 1.5:
                anomalies_detected += 1
        if anomalies_detected > 10:
            drift_status = (
                f"Warning: Data drift detected. "
                f"{anomalies_detected}/{len(recent_levels)} levels exceed 1.5x danger threshold."
            )

    # 5. Prediction count from DB
    total_predictions = db.query(Prediction).count()

    # 6. System metrics (psutil or wmic)
    sys_metrics = get_system_metrics()
    latency_ms = round((time.time() - start_time) * 1000, 2)

    return {
        "status": "Healthy" if db_status == "Healthy" and scheduler_status == "Healthy" else "Warning",
        "api_latency_ms": latency_ms,
        "database_health": db_status,
        "scheduler_status": scheduler_status,
        "data_drift": drift_status,
        "model_drift": model_drift_status,
        "system_metrics": sys_metrics,
        "inference_latency_avg_ms": get_last_inference_latency(),  # measured by /predict
        "prediction_count": total_predictions,
        "last_updated": latest_lvl.ts.strftime("%Y-%m-%d %H:%M:%S") if latest_lvl else None
    }
