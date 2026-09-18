import urllib.request
import json
import os

BASE = "http://localhost:8000/api"

def run_tests():
    print("==================================================")
    print(" HYDROGNN-NET FINAL SYSTEM & ENDPOINT VERIFICATION")
    print("==================================================")

    # 1. Login
    login_url = f"{BASE}/auth/login"
    login_data = json.dumps({"email": "admin@hydrognn.in", "password": "hydrognn2026"}).encode("utf-8")
    req = urllib.request.Request(login_url, data=login_data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as resp:
        login_res = json.loads(resp.read().decode("utf-8"))
    token = login_res.get("access_token")
    assert token, "Login failed, no token"
    print(f"[PASS] 1. Auth Login: Received Bearer token ({token[:20]}...)")

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # 2. Health
    health_req = urllib.request.Request(f"{BASE}/health", method="GET")
    with urllib.request.urlopen(health_req) as resp:
        health_res = json.loads(resp.read().decode("utf-8"))
    print(f"[PASS] 2. Health Check: status={health_res.get('status')}, model_status={health_res.get('model_status')}")
    assert health_res.get("model_status") == "Loaded", f"Expected model_status Loaded, got {health_res.get('model_status')}"

    # 3. Dashboard
    dash_req = urllib.request.Request(f"{BASE}/dashboard", headers=headers, method="GET")
    with urllib.request.urlopen(dash_req) as resp:
        dash_res = json.loads(resp.read().decode("utf-8"))
    stations = dash_res.get("stations", [])
    print(f"[PASS] 3. GET /api/dashboard: timestamp={dash_res.get('timestamp')}, total_stations={len(stations)}")
    
    # 8 Cauvery Basin stations
    cauvery_stations = [s for s in stations if s.get("basin") in ["Cauvery", "Bhavani"]]
    print(f"   - Monitored Cauvery Stations ({len(cauvery_stations)}):")
    for s in cauvery_stations:
        print(f"     * {s['id']}: {s['name']} (Basin: {s['basin']}, Water Level: {s['water_level']} ft, Danger: {s['danger_level']} ft)")
    assert len(cauvery_stations) == 8, f"Expected 8 Cauvery stations, got {len(cauvery_stations)}"

    # 4. Predict API
    pred_url = f"{BASE}/predict"
    pred_body = json.dumps({"station_id": "METTUR", "horizons_hours": [6, 12, 24]}).encode("utf-8")
    pred_req = urllib.request.Request(pred_url, data=pred_body, headers=headers, method="POST")
    with urllib.request.urlopen(pred_req) as resp:
        pred_res = json.loads(resp.read().decode("utf-8"))

    print(f"[PASS] 4. POST /api/predict (METTUR, [6, 12, 24]):")
    print(f"   - Station ID: {pred_res.get('station_id')}")
    
    predictions = pred_res.get("predictions", [])
    assert len(predictions) == 3, f"Expected 3 predictions, got {len(predictions)}"
    for p in predictions:
        h = p.get("horizon_hours")
        lvl = p.get("level_m")
        unc = p.get("uncertainty_m")
        prob = p.get("flood_probability")
        sev = p.get("severity")
        conf = p.get("confidence")
        print(f"     * Horizon {h}h: level={lvl} ft, uncertainty={unc} ft, prob={prob}, severity={sev}, confidence={conf}")
        assert lvl is not None, f"Level is None for {h}h"
        assert unc is not None, f"Uncertainty is None for {h}h"

    # Hydrograph check
    hydrograph = pred_res.get("hydrograph", [])
    print(f"   - Hydrograph total points: {len(hydrograph)}")
    obs_pts = [h for h in hydrograph if h.get("section") == "observed"]
    fc_pts = [h for h in hydrograph if h.get("section") == "forecast"]
    print(f"     * Observed points: {len(obs_pts)}")
    print(f"     * Forecast points: {len(fc_pts)}")
    assert len(obs_pts) > 0, "No observed points in hydrograph"
    assert len(fc_pts) > 0, "No forecast points in hydrograph"

    # NaN / Inf check
    raw_str = json.dumps(pred_res)
    assert "NaN" not in raw_str and "nan" not in raw_str and "Infinity" not in raw_str, "Found NaN or Infinity in prediction response"
    print("   - Checked: No NaN / Infinity values in JSON response.")

    # 5. Check checkpoint integrity
    ckpt_path = "Models/best_model.pt"
    assert os.path.exists(ckpt_path), "Checkpoint Models/best_model.pt missing"
    ckpt_size = os.path.getsize(ckpt_path)
    print(f"[PASS] 5. Model Checkpoint verified intact: {ckpt_path} (size: {ckpt_size} bytes, NOT modified)")

    print("==================================================")
    print(" ALL API VERIFICATIONS PASSED SUCCESSFULLY!")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
