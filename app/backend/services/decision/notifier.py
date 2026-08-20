import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from app.backend.services.db.models import Alert
from app.backend.services.logging_manager import alerts_logger

def dispatch_emergency_alerts(db: Session, alerts_list: list):
    """
    Logs alerts in the database and dispatches simulated email and SMS messages to emergency officers.
    Args:
        alerts_list: List of dicts with: station_id, message, severity, recommended_actions
    """
    dispatched_alerts = []
    
    for a in alerts_list:
        alert_id = f"ALT_{uuid.uuid4().hex[:8].upper()}"
        
        # Save to database
        db_alert = Alert(
            id=alert_id,
            station_id=a["station_id"],
            prediction_id=None,
            sent_at=datetime.utcnow(),
            channel="SMS/EMAIL/DASHBOARD",
            message=a["message"],
            severity=a["severity"]
        )
        db.add(db_alert)
        
        # Simulate SMS and Email dispatch
        alerts_logger.warning(
            f"DISPATCH SUCCESS [{alert_id}] to admin@hydrognn.in and Control Room SMS (+91-9988776655):\n"
            f"  [Severity]: {a['severity']}\n"
            f"  [Message]: {a['message']}\n"
            f"  [Recommended Action]: {a.get('recommended_actions', 'Take necessary flood precautions.')}"
        )
        
        dispatched_alerts.append(db_alert)
        
    db.commit()
    return dispatched_alerts
