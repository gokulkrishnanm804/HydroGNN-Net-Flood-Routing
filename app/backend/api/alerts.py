import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.backend.services.db.connection import get_db
from app.backend.services.db.models import Alert
from app.backend.auth.jwt_handler import verify_access_token

router = APIRouter(prefix="/alerts", tags=["alerts"])
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    payload = verify_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload

@router.get("")
def get_active_alerts(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    from datetime import datetime, timedelta
    one_day_ago = datetime.utcnow() - timedelta(hours=24)

    alerts = (
        db.query(Alert)
        .filter(Alert.sent_at >= one_day_ago)
        .order_by(Alert.sent_at.desc())
        .limit(50)
        .all()
    )

    alerts_list = []
    for al in alerts:
        station = al.station
        alerts_list.append({
            "id": al.id,
            "station_id": al.station_id,
            "station_name": station.name,
            "basin": station.river,
            "timestamp": al.sent_at.strftime("%Y-%m-%d %H:%M:%S"),
            "severity": al.severity,
            "type": "FLOOD_WARNING",
            "message": al.message
        })

    return alerts_list


@router.get("/history")
def get_historical_alerts(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    alerts = (
        db.query(Alert)
        .order_by(Alert.sent_at.desc())
        .limit(100)
        .all()
    )

    alerts_list = []
    for al in alerts:
        station = al.station
        alerts_list.append({
            "id": al.id,
            "station_id": al.station_id,
            "station_name": station.name,
            "basin": station.river,
            "timestamp": al.sent_at.strftime("%Y-%m-%d %H:%M:%S"),
            "severity": al.severity,
            "type": "FLOOD_WARNING",
            "message": al.message
        })

    return alerts_list

