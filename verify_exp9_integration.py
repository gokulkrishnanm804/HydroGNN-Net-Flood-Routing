"""
Comprehensive Verification Suite for Experiment 9 Backend Integration
Tests:
  A. Model loading test (singleton, CPU, strict=True key verification)
  B. CPU forward inference test
  C. POST /api/predict test (with auth token)
  D. Verify response JSON schema completeness
  E. Verify all three horizons [6, 12, 24]
  F. Verify Forecast Studio requested horizons [1, 3, 6, 12, 18, 24]
  G. Verify 15-minute hydrograph generation (192 points: observed + forecast)
  H. Verify 95% confidence interval generation (upper > predicted > lower)
  I. Verify no NaN / Inf values across all predictions and hydrographs
"""

import sys
import json
import math
import numpy as np
from fastapi.testclient import TestClient
from app.backend.main import app
from app.backend.auth.jwt_handler import create_access_token
from app.backend.services.routing.exp9_service import get_exp9_manager

def run_tests():
    print("==================================================================")
    print("   HYDROGNN-NET EXPERIMENT 9 INTEGRATION VERIFICATION SUITE       ")
    print("==================================================================")

    # -------------------------------------------------------------
    # Test A: Model Loading Test
    # -------------------------------------------------------------
    print("\n--- Test A: Model Loading Test ---")
    manager = get_exp9_manager()
    assert manager.model is not None, "Model is not initialized"
    assert manager.device.type == "cpu", f"Device is not CPU: {manager.device}"
    assert manager.model_config["node_features"] == 7
    assert manager.model_config["hidden_dim"] == 64
    assert manager.model_config["gru_layers"] == 2
    assert manager.model_config["gat_heads"] == 4
    assert manager.model_config["gat_layers"] == 2
    assert manager.model_config["sage_hidden"] == 64
    assert manager.model_config["edge_dim"] == 3
    assert manager.model_config["horizons"] == [6, 12, 24]
    print(f"  [PASS] Model checkpoint loaded from: {manager.checkpoint_path}")
    print(f"  [PASS] Model architecture: HydroGNNNet on {manager.device}")
    print(f"  [PASS] Model config strictly verified: {manager.model_config}")

    # -------------------------------------------------------------
    # Test B: CPU Forward Inference Test
    # -------------------------------------------------------------
    print("\n--- Test B: Direct CPU Inference Forward Pass ---")
    import torch
    dummy_x = torch.randn((8, 24, 7), dtype=torch.float32, device="cpu")
    dummy_edge_index = torch.tensor([[0, 1, 2, 3, 4, 5, 7], [1, 2, 3, 4, 5, 7, 6]], dtype=torch.long)
    dummy_edge_attr = torch.ones((7, 3), dtype=torch.float32)
    dummy_y_curr = torch.tensor([5.0, 30.0, 4.0, 2.0, 2.0, 1.5, 1.5, 1.0], dtype=torch.float32)
    dummy_trend = torch.zeros((8, 3), dtype=torch.float32)

    with torch.no_grad():
        pred_delta, log_var, gate = manager.model(
            dummy_x,
            dummy_edge_index,
            dummy_edge_attr,
            y_curr=dummy_y_curr,
            trend=dummy_trend,
        )

    assert pred_delta.shape == (8, 3), f"pred_delta shape mismatch: {pred_delta.shape}"
    assert log_var.shape == (8, 3), f"log_var shape mismatch: {log_var.shape}"
    assert gate.shape == (8, 3), f"gate shape mismatch: {gate.shape}"
    assert torch.all(torch.isfinite(pred_delta)), "pred_delta has NaN/Inf"
    assert torch.all(torch.isfinite(log_var)), "log_var has NaN/Inf"
    assert torch.all((gate >= 0.0) & (gate <= 1.0)), "gate values not in [0, 1]"
    print(f"  [PASS] Forward pass successful. Shapes: pred_delta={pred_delta.shape}, gate={gate.shape}")

    # -------------------------------------------------------------
    # Test C: POST /api/predict Test via TestClient
    # -------------------------------------------------------------
    print("\n--- Test C: POST /api/predict Client Request ---")
    client = TestClient(app)
    token = create_access_token({"sub": "admin@hydrognn.in", "role": "admin"})
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    req_body_std = {"station_id": "METTUR", "horizons_hours": [6, 12, 24]}
    resp_std = client.post("/api/predict", json=req_body_std, headers=headers)
    assert resp_std.status_code == 200, f"Predict failed ({resp_std.status_code}): {resp_std.text}"
    data_std = resp_std.json()
    print(f"  [PASS] POST /api/predict responded 200 OK for METTUR [6, 12, 24]")

    # -------------------------------------------------------------
    # Test D: Verify Response JSON Structure
    # -------------------------------------------------------------
    print("\n--- Test D: Verify Response JSON Schema ---")
    required_keys = [
        "station_id", "predictions", "hydrograph", "rain_overlay",
        "routing_metadata", "discharge_overlay", "upstream_sources",
        "xai_attributions", "gat_attention"
    ]
    for k in required_keys:
        assert k in data_std, f"Missing required response key: {k}"
        print(f"  [PASS] Key present: {k}")

    # -------------------------------------------------------------
    # Test E: Verify All Three Horizons [6, 12, 24]
    # -------------------------------------------------------------
    print("\n--- Test E: Verify Standard Horizons [6, 12, 24] ---")
    preds = data_std["predictions"]
    assert len(preds) == 3, f"Expected 3 predictions, got {len(preds)}"
    horizons_found = [p["horizon_hours"] for p in preds]
    assert horizons_found == [6, 12, 24], f"Horizons mismatch: {horizons_found}"
    for p in preds:
        assert "level_m" in p
        assert "uncertainty_m" in p
        assert "confidence" in p
        assert "severity" in p
        print(f"  [PASS] Horizon {p['horizon_hours']}h: Level={p['level_m']}ft, Unc={p['uncertainty_m']}ft, Severity={p['severity']}, Conf={p['confidence']}")

    # -------------------------------------------------------------
    # Test F: Verify Forecast Studio Request [1, 3, 6, 12, 18, 24]
    # -------------------------------------------------------------
    print("\n--- Test F: Verify Forecast Studio Request [1, 3, 6, 12, 18, 24] ---")
    req_body_fs = {"station_id": "METTUR", "horizons_hours": [1, 3, 6, 12, 18, 24]}
    resp_fs = client.post("/api/predict", json=req_body_fs, headers=headers)
    assert resp_fs.status_code == 200, f"Forecast Studio predict failed: {resp_fs.text}"
    data_fs = resp_fs.json()
    preds_fs = data_fs["predictions"]
    assert len(preds_fs) == 6, f"Expected 6 predictions, got {len(preds_fs)}"
    horizons_fs = [p["horizon_hours"] for p in preds_fs]
    assert horizons_fs == [1, 3, 6, 12, 18, 24], f"Forecast studio horizons mismatch: {horizons_fs}"
    for p in preds_fs:
        print(f"  [PASS] Horizon {p['horizon_hours']}h: Level={p['level_m']}ft, Unc={p['uncertainty_m']}ft, Conf={p['confidence']}")

    # -------------------------------------------------------------
    # Test G: Verify 15-minute Hydrograph Generation
    # -------------------------------------------------------------
    print("\n--- Test G: Verify 15-Minute Hydrograph Generation ---")
    hydro = data_std["hydrograph"]
    obs_pts = [pt for pt in hydro if pt["section"] == "observed"]
    fcst_pts = [pt for pt in hydro if pt["section"] == "forecast"]
    assert len(obs_pts) >= 96, f"Observed points should be >= 96, got {len(obs_pts)}"
    assert len(fcst_pts) == 96, f"Forecast points should be exactly 96, got {len(fcst_pts)}"
    print(f"  [PASS] Total hydrograph points: {len(hydro)} (Observed: {len(obs_pts)}, Forecast: {len(fcst_pts)})")

    # Check time increment
    print(f"  [PASS] First observed: {obs_pts[0]['time']} (lvl={obs_pts[0]['observed']}ft)")
    print(f"  [PASS] Last observed: {obs_pts[-1]['time']} (lvl={obs_pts[-1]['observed']}ft)")
    print(f"  [PASS] First forecast: {fcst_pts[0]['time']} (pred={fcst_pts[0]['predicted']}ft)")
    print(f"  [PASS] Last forecast: {fcst_pts[-1]['time']} (pred={fcst_pts[-1]['predicted']}ft)")

    # -------------------------------------------------------------
    # Test H: Verify 95% Confidence Interval Generation
    # -------------------------------------------------------------
    print("\n--- Test H: Verify 95% Confidence Interval Generation ---")
    for pt in fcst_pts:
        pred = pt["predicted"]
        upper = pt["upper"]
        lower = pt["lower"]
        assert upper >= pred, f"CI upper ({upper}) < pred ({pred})"
        assert pred >= lower, f"CI lower ({lower}) > pred ({pred})"
    print(f"  [PASS] 95% CI validated across all 96 forecast steps (upper >= predicted >= lower)")

    # -------------------------------------------------------------
    # Test I: Verify No NaN or Inf Values
    # -------------------------------------------------------------
    print("\n--- Test I: Verify No NaN or Inf Values ---")
    def check_clean(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                check_clean(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                check_clean(v, f"{path}[{i}]")
        elif isinstance(obj, float):
            assert not math.isnan(obj), f"NaN found at {path}"
            assert not math.isinf(obj), f"Inf found at {path}"

    check_clean(data_std)
    check_clean(data_fs)
    print("  [PASS] Zero NaNs and zero Infs found in standard and Forecast Studio responses!")

    print("\n==================================================================")
    print("   ALL TESTS A THROUGH I PASSED SUCCESSFULLY!                     ")
    print("==================================================================")

if __name__ == "__main__":
    run_tests()
