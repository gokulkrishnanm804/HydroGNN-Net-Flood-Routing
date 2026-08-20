import asyncio
import os
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Imports
from app.backend.api import predict, dashboard, alerts, chat, monitoring, replay, satellite
from app.backend.auth.jwt_handler import create_access_token
from app.backend.services.db.connection import initialize_database, load_dotenv
from app.backend.services.scheduler.cron import start_realtime_scheduler

# Load .env before anything else so env vars are available
_project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(_project_dir)

# ── Lifespan (replaces deprecated @on_event("startup")) ──────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting HydroGNN-Net backend services...")
    initialize_database()
    await start_realtime_scheduler()
    asyncio.create_task(_startup_satellite_ingest())
    yield  # server is now running
    # (shutdown logic can go here if needed)

app = FastAPI(
    title="HydroGNN-Net API",
    description="Spatio-Temporal GNN-Transformer Flood Routing Decision Support Service",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS — Issue #2 Fix ───────────────────────────────────────────────────────
# CORS_ORIGINS env var: comma-separated list of allowed origins.
# Defaults to Vite dev server ports. Set to your domain in production.
# NOTE: allow_origins=["*"] + allow_credentials=True is rejected by browsers
# in production — we must always use explicit origins here.
_raw_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:5174,http://localhost:3000"
)
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(predict.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(monitoring.router, prefix="/api")
app.include_router(replay.router, prefix="/api")
app.include_router(satellite.router, prefix="/api")

class LoginRequest(BaseModel):
    email: str
    password: str

@app.post("/api/auth/login")
def login(req: LoginRequest):
    # Static credentials for the control room dashboard demo
    if req.email == "admin@hydrognn.in" and req.password == "hydrognn2026":
        token = create_access_token({"sub": req.email, "role": "admin"})
        return {"access_token": token, "token_type": "bearer"}
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. Use admin@hydrognn.in / hydrognn2026",
            headers={"WWW-Authenticate": "Bearer"},
        )

@app.get("/api/health")
def health_check():
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(backend_dir)
    model_path = os.path.join(project_dir, "training", "checkpoints", "best_model.pt")
    
    if os.path.exists(model_path):
        model_status = "Loaded"
    else:
        model_status = "Unavailable: best_model.pt not found"
        
    return {
        "status": "Healthy",
        "model_status": model_status
    }

async def _startup_satellite_ingest():
    """Run one satellite ingestion pass at startup (non-blocking background task)."""
    from datetime import datetime
    from app.backend.services.db.connection import SessionLocal
    from app.backend.services.ingestion.satellite_api import fetch_and_store_satellite

    await asyncio.sleep(5)  # let the DB fully initialize first
    db = SessionLocal()
    try:
        startup_ts = datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
        print(f"[Startup] Triggering satellite ingestion pass at ts={startup_ts}")
        await asyncio.to_thread(fetch_and_store_satellite, db, startup_ts)
        print("[Startup] Satellite ingestion complete.")
    except Exception as e:
        print(f"[Startup] Satellite ingestion failed (non-fatal): {e}")
    finally:
        db.close()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
