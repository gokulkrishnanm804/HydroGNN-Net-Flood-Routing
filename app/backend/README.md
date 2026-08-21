# HydroGNN-Net Backend API

FastAPI-powered REST API and inference service for the HydroGNN-Net Flood Routing & Early Warning Decision Support System.

---

## 📋 Prerequisites

- **Python**: Version `3.10` to `3.12` (Python 3.11 recommended)
- **Node.js / Frontend**: Running on `http://localhost:3000` (Next.js)

---

## 🚀 Quick Start Guide

Run all commands from the **root directory of the project** (`new_project/`):

### 1. (Optional) Create & Activate Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

### 2. Install Dependencies

```bash
pip install -r app/backend/requirements.txt
```

---

### 3. Configure Environment Variables

Create a `.env` file in the project root by copying the example:

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

**Linux / macOS:**
```bash
cp .env.example .env
```

---

### 4. Run the Backend Server

> **IMPORTANT**: Run the command from the **root of the workspace** so Python module paths (`app.backend.*`) resolve properly.

#### Development Mode (with Auto-Reload)
```bash
python -m uvicorn app.backend.main:app --host 0.0.0.0 --port 8000 --reload
```

#### Production Mode
```bash
python -m uvicorn app.backend.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 🌐 Server Endpoints & URLs

Once the server is running:

| Description | URL |
| :--- | :--- |
| **API Base URL** | `http://localhost:8000` |
| **Interactive Swagger Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) |
| **ReDoc Documentation** | [http://localhost:8000/redoc](http://localhost:8000/redoc) |
| **Health Check** | [http://localhost:8000/api/health](http://localhost:8000/api/health) |

---

## 🔐 Default Demo Credentials

The backend includes built-in credentials for the Control Room Dashboard demo:

- **Email**: `admin@hydrognn.in`
- **Password**: `hydrognn2026`

---

## 📡 Key API Routes

- `POST /api/auth/login` — Authenticate and retrieve JWT bearer token
- `GET /api/health` — Service and GNN model weights health check
- `GET /api/dashboard` — Live gauge stations, reservoir levels, and telemetry
- `POST /api/predict` — Hydrograph flood convolved prediction with GAT attention & XAI
- `GET /api/alerts` — Active flood warnings and alert logs
- `GET /api/alerts/history` — Historical alerts archive
- `POST /api/chat` — AI Hydro-Chatbot assistant
- `GET /api/satellite` — Satellite catalog metadata (NDVI / HLS scenes)
- `GET /api/monitoring/diagnostics` — System metrics, inference latency, drift detection
- `GET /api/replay/events` — Archived historical flood events
- `POST /api/replay/trigger` — Trigger flood event replay simulation

---

## 🛠️ Troubleshooting

### 1. `Failed to fetch` Error on Frontend
If the frontend shows `TypeError: Failed to fetch`, the backend is not running. Start the backend with:
```bash
python -m uvicorn app.backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Port 8000 already in use
**Windows:**
```powershell
Get-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess | Stop-Process -Force
```
**Linux / macOS:**
```bash
lsof -ti:8000 | xargs kill -9
```

### 3. Model Checkpoint Warning (`model_status: Unavailable`)
If `best_model.pt` is not found, the backend will still run and serve simulated predictions. To use trained weights, place your trained checkpoint at:
```
training/checkpoints/best_model.pt
```
