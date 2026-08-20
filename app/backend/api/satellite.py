"""
GET /api/satellite
Returns the most recent Sentinel-2 scene metadata for each station from satellite_images table.
Also triggers an on-demand ingestion pass if the table has no rows.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from datetime import datetime

from app.backend.services.db.connection import get_db
from app.backend.services.db.models import SatelliteImage, RiverStation
from app.backend.auth.jwt_handler import verify_access_token

router   = APIRouter(prefix="/satellite", tags=["satellite"])
security = HTTPBearer()

# Guard: prevent launching duplicate ingestion threads
_ingestion_running = False

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    payload = verify_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


@router.get("")
def get_satellite_data(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Returns latest Sentinel-2 scene per station (most recent capture_date).
    If no rows exist, triggers a background ingestion pass and returns an
    informational empty list rather than crashing.
    """
    # Check total row count
    total_rows = db.query(SatelliteImage).count()

    if total_rows == 0:
        # Trigger an on-demand ingestion pass in the background (non-blocking)
        # Guard: only launch one thread at a time
        global _ingestion_running
        import threading

        if not _ingestion_running:
            _ingestion_running = True

            def _ingest_background():
                global _ingestion_running
                from app.backend.services.db.connection import SessionLocal
                from app.backend.services.ingestion.satellite_api import fetch_and_store_satellite
                bg_db = SessionLocal()
                try:
                    # Force ts to noon so the daily time-gate opens
                    ts = datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
                    fetch_and_store_satellite(bg_db, ts)
                except Exception as e:
                    print(f"[Satellite] Background ingestion error: {e}")
                finally:
                    bg_db.close()
                    _ingestion_running = False   # allow re-trigger after completion

            t = threading.Thread(target=_ingest_background, daemon=True)
            t.start()
            msg = "No satellite scenes in database. Ingestion triggered. Refresh in 60-90 seconds."
        else:
            msg = "Ingestion already in progress. Please wait 60-90 seconds and refresh."

        return {
            "status": "ingesting",
            "message": msg,
            "scenes": [],
            "total_scenes": 0,
            "source": "Copernicus STAC / OData",
        }

    # Get latest scene per station using subquery
    from sqlalchemy import func

    latest_subq = (
        db.query(
            SatelliteImage.station_id,
            func.max(SatelliteImage.capture_date).label("max_date")
        )
        .group_by(SatelliteImage.station_id)
        .subquery()
    )

    scenes = (
        db.query(SatelliteImage)
        .join(
            latest_subq,
            (SatelliteImage.station_id == latest_subq.c.station_id) &
            (SatelliteImage.capture_date == latest_subq.c.max_date)
        )
        .all()
    )

    result = []
    for s in scenes:
        station = db.query(RiverStation).filter(RiverStation.id == s.station_id).first()
        result.append({
            "id":           s.id,
            "station_id":   s.station_id,
            "station_name": station.name if station else s.station_id,
            "basin":        station.river if station else "Unknown",
            "lat":          station.lat if station else 0,
            "lon":          station.lon if station else 0,
            "capture_date": str(s.capture_date),
            "source":       s.source,
            "storage_path": s.storage_path,
            "age_days": (datetime.utcnow().date() - s.capture_date).days
                        if s.capture_date else None,
        })

    return {
        "status": "ok",
        "message": f"{len(result)} latest Sentinel-2 scenes returned.",
        "scenes": result,
        "total_scenes": total_rows,
        "source": "Copernicus OData / STAC",
        "last_ingested": max((r["capture_date"] for r in result), default=None),
    }
