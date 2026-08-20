import re
import time
from fastapi import Request, HTTPException, status
from app.backend.services.logging_manager import api_logger

# In-memory token bucket rate limiter cache
RATE_LIMIT_CACHE = {}

def check_rate_limit(request: Request):
    """
    Limits clients to 30 requests per minute to safeguard heavy GPU/CPU GNN inference resources.
    """
    client_ip = request.client.host if request.client else "unknown"
    curr_time = time.time()
    
    # Initialize cache record
    if client_ip not in RATE_LIMIT_CACHE:
        RATE_LIMIT_CACHE[client_ip] = []
        
    # Filter out requests older than 60 seconds
    RATE_LIMIT_CACHE[client_ip] = [t for t in RATE_LIMIT_CACHE[client_ip] if curr_time - t < 60]
    
    if len(RATE_LIMIT_CACHE[client_ip]) >= 30:
        api_logger.warning(f"Rate limit exceeded for client IP: {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. GNN inference resources are rate-limited to 30 requests/min."
        )
        
    RATE_LIMIT_CACHE[client_ip].append(curr_time)

def validate_station_id(station_id: str) -> str:
    """
    Sanitizes and validates input station IDs.
    """
    if not station_id:
        raise HTTPException(status_code=400, detail="Station ID is required.")
        
    # Match alphanumeric + underscores, max length 30
    if not re.match(r"^[A-Z0-9_]{3,30}$", station_id.upper()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid Station ID format. Must contain only letters, numbers, and underscores (3-30 chars)."
        )
        
    return station_id.upper()
