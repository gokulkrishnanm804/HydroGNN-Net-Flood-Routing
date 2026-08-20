import json
import urllib.request
import urllib.parse

def test_backend():
    print("Verifying FastAPI backend endpoints...")
    base_url = "http://127.0.0.1:8000/api"
    
    # 1. Test Login
    login_url = f"{base_url}/auth/login"
    login_data = json.dumps({
        "email": "admin@hydrognn.in",
        "password": "hydrognn2026"
    }).encode("utf-8")
    
    req = urllib.request.Request(
        login_url,
        data=login_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as res:
            response = json.loads(res.read().decode("utf-8"))
            token = response.get("access_token")
            print("[OK] Login successful. Received token.")
    except Exception as e:
        print("[ERROR] Login failed:", str(e))
        return
        
    auth_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # 2. Test Health Check
    try:
        health_req = urllib.request.Request(f"{base_url}/health", method="GET")
        with urllib.request.urlopen(health_req) as res:
            print("[OK] Health check successful:", res.read().decode("utf-8"))
    except Exception as e:
        print("[ERROR] Health check failed:", str(e))
        
    # 3. Test Dashboard Summary
    try:
        dash_req = urllib.request.Request(
            f"{base_url}/dashboard",
            headers=auth_headers,
            method="GET"
        )
        with urllib.request.urlopen(dash_req) as res:
            dash_data = json.loads(res.read().decode("utf-8"))
            print(f"[OK] Dashboard active. Timestamp: {dash_data['timestamp']}. Warnings: {dash_data['active_warnings']}.")
    except Exception as e:
        print("[ERROR] Dashboard summary failed:", str(e))
        
    # 4. Test Predictions
    try:
        pred_url = f"{base_url}/predict"
        pred_data = json.dumps({
            "station_id": "METTUR",
            "horizons_hours": [6, 24]
        }).encode("utf-8")
        
        pred_req = urllib.request.Request(
            pred_url,
            data=pred_data,
            headers=auth_headers,
            method="POST"
        )
        with urllib.request.urlopen(pred_req) as res:
            pred_res = json.loads(res.read().decode("utf-8"))
            print(f"[OK] Prediction endpoint active. Received {len(pred_res['predictions'])} predictions. Hydrograph elements: {len(pred_res['hydrograph'])}.")
    except Exception as e:
        print("[ERROR] Prediction endpoint failed:", str(e))
        
    # 5. Test Chat Assistant
    try:
        chat_url = f"{base_url}/chat"
        chat_data = json.dumps({
            "message": "Are there any active warning alerts?"
        }).encode("utf-8")
        
        chat_req = urllib.request.Request(
            chat_url,
            data=chat_data,
            headers=auth_headers,
            method="POST"
        )
        with urllib.request.urlopen(chat_req) as res:
            chat_res = json.loads(res.read().decode("utf-8"))
            print("[OK] Chat assistant query response:")
            print("  Query:", chat_res["query"])
            print("  Response:", chat_res["response"][:120], "...")
    except Exception as e:
        print("[ERROR] Chat assistant failed:", str(e))
        
    print("\nVerification completed.")

if __name__ == "__main__":
    test_backend()
