import urllib.request, json, time

BASE = "http://localhost:8000/api"

def req(method, path, data=None, token=None):
    url = BASE + path
    hdrs = {"Content-Type": "application/json"}
    if token:
        hdrs["Authorization"] = "Bearer " + token
    body = json.dumps(data).encode() if data else None
    r = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    t0 = time.time()
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return json.loads(resp.read()), round((time.time()-t0)*1000)
    except Exception as e:
        return {"error": str(e)}, 0

print("=== FULL SYSTEM VERIFICATION ===")

# 1. Auth
res, ms = req("POST", "/auth/login", {"email": "admin@hydrognn.in", "password": "hydrognn2026"})
token = res.get("access_token")
print("1. AUTH:", "PASS" if token else "FAIL", ms, "ms")

# 2. Dashboard - verify data_source field exists
res, ms = req("GET", "/dashboard", token=token)
stations = res.get("stations", [])
sources = set(s.get("data_source", "missing") for s in stations)
has_ds = all("data_source" in s for s in stations)
print("2. DASHBOARD: stations=" + str(len(stations)) + " has_data_source=" + str(has_ds) + " sources=" + str(sources) + " " + str(ms) + "ms")

# 3. Predict METTUR - check real XAI (no hardcoded 72)
res, ms = req("POST", "/predict", {"station_id": "METTUR", "horizons_hours": [6, 12, 24]}, token)
xai = res.get("xai_attributions", {})
gat = res.get("gat_attention", [])
has_old_key = "spatial_attention" in res
total_pct = sum(xai.values()) if xai else 0
fake_check = xai.get("Upstream Reservoir Release") == 72
print("3a. PREDICT/XAI features=" + str(list(xai.keys())))
print("    total_pct=" + str(total_pct) + " fake_72=" + str(fake_check) + " old_key=" + str(has_old_key))
print("3b. GAT attention: " + str(gat))

# 4. Predict ERODE
res2, ms2 = req("POST", "/predict", {"station_id": "ERODE", "horizons_hours": [24]}, token)
xai2 = res2.get("xai_attributions", {})
gat2 = res2.get("gat_attention", [])
print("4. ERODE XAI=" + str(xai2) + " GAT=" + str(gat2) + " " + str(ms2) + "ms")

# 5. Alerts
res3, ms3 = req("GET", "/alerts", token=token)
print("5. ALERTS: count=" + str(len(res3)) + " " + str(ms3) + "ms")

# 6. DB check via monitoring
res4, ms4 = req("GET", "/monitoring/diagnostics", token=token)
db_stats = res4.get("database_stats", {})
print("6. DB STATS: " + str(db_stats))

print("")
print("=== VERIFICATION COMPLETE ===")
