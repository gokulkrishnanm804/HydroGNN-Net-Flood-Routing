import os
import json
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from datasets.loaders.river_dataset import RiverBasinDataset
from models.routing_model import HydroGNNNet
from models.physics.pinn_loss import PhysicsInformedLoss

def calculate_nse(obs, pred):
    """
    Calculates Nash-Sutcliffe Efficiency.
    """
    # obs: [N], pred: [N]
    mean_obs = torch.mean(obs)
    denominator = torch.sum((obs - mean_obs) ** 2)
    numerator = torch.sum((obs - pred) ** 2)
    if denominator == 0:
        return 0.0
    return (1.0 - (numerator / denominator)).item()

def classify_severity(level, danger_level):
    """
    Classifies water level into 5 severity indices:
    0: Safe (< 40% danger_level)
    1: Low (40% - 70% danger_level)
    2: Moderate (70% - 90% danger_level)
    3: High (90% - 100% danger_level)
    4: Severe (>= 100% danger_level)
    """
    ratio = level / danger_level
    if ratio < 0.4:
        return 0
    elif ratio < 0.7:
        return 1
    elif ratio < 0.9:
        return 2
    elif ratio < 1.0:
        return 3
    else:
        return 4

def train_model(epochs=5, batch_size=8, lr=1e-3, physics_weight=0.1, classification_weight=0.5):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Training HydroGNN-Net model on: {device}")
    
    # Path resolve
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    
    data_path = os.path.join(project_dir, "datasets", "processed", "flood_data.csv")
    graph_path = os.path.join(project_dir, "datasets", "processed", "graph_topology.json")
    
    # Check dataset existence
    if not os.path.exists(data_path) or not os.path.exists(graph_path):
        print("Data files not found. Please run datasets/simulator.py first.")
        return
        
    # Datasets
    train_dataset = RiverBasinDataset(data_path, graph_path, lookback=24, horizon=96, step=2, mode="train")
    val_dataset = RiverBasinDataset(data_path, graph_path, lookback=24, horizon=96, step=4, mode="val")
    
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
    
    # Station danger levels for severity target generation
    danger_levels = torch.tensor([s["danger_level"] for s in train_dataset.stations], device=device)
    
    # Save scaling statistics for backend inference
    checkpoint_dir = os.path.join(project_dir, "training", "checkpoints")
    os.makedirs(checkpoint_dir, exist_ok=True)
    
    stats = {
        "means": train_dataset.means,
        "stds": train_dataset.stds
    }
    with open(os.path.join(checkpoint_dir, "scaling_stats.json"), "w") as f:
        json.dump(stats, f, indent=2)
    print("Saved scaling statistics.")
    
    # Model
    model = HydroGNNNet(
        node_in_dim=8,
        weather_in_dim=3,
        hidden_dim=64,
        heads=4,
        num_layers=2, # Keep lightweight for faster training
        dropout=0.1
    ).to(device)
    
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    
    # Loss modules
    criterion_mse = nn.MSELoss()
    criterion_ce = nn.CrossEntropyLoss()
    physics_loss_fn = PhysicsInformedLoss(step_minutes=15)
    
    best_nse = -999.0
    
    for epoch in range(epochs):
        model.train()
        total_loss = 0.0
        total_mse_lvl = 0.0
        total_mse_q = 0.0
        total_phys = 0.0
        total_cls = 0.0
        
        for batch in train_loader:
            hist_x = batch["hist_x"].to(device) # [B, L, N, 8]
            fut_w = batch["fut_w"].to(device)   # [B, H, N, 3]
            fut_y = batch["fut_y"].to(device)   # [B, H, N]
            fut_q = batch["fut_q"].to(device)   # [B, H, N]
            edge_index = batch["edge_index"][0].to(device) # [2, E]
            edge_travel_times = batch["edge_travel_times"][0].to(device) # [E]
            
            optimizer.zero_grad()
            
            # Forward pass
            pred_y_norm, pred_q_norm, pred_sev_logits = model(hist_x, fut_w, edge_index, edge_travel_times)
            
            # Scale back predictions to compute physical loss and standard targets
            # Denormalize level: val * std + mean
            mean_y = train_dataset.means["water_level"]
            std_y = train_dataset.stds["water_level"]
            mean_q = train_dataset.means["discharge"]
            std_q = train_dataset.stds["discharge"]
            
            pred_y = pred_y_norm * std_y + mean_y
            pred_q = pred_q_norm * std_q + mean_q
            
            # Extract historical discharge for physics loss
            # hist_x contains normalized discharge in the last index: hist_x[:, :, :, 7]
            hist_q = hist_x[:, :, :, 7] * std_q + mean_q
            
            # 1. Level MSE Loss
            target_y_norm = (fut_y - mean_y) / std_y
            loss_mse_lvl = criterion_mse(pred_y_norm, target_y_norm)
            
            # 2. Discharge MSE Loss
            target_q_norm = (fut_q - mean_q) / std_q
            loss_mse_q = criterion_mse(pred_q_norm, target_q_norm)
            
            # 3. Physics Informed Loss
            # weather forecast rain is in fut_w[:, :, :, 1] (rain_forecast_24h or similar)
            rain_fc = fut_w[:, :, :, 1] # shape [B, H, N]
            loss_phys = physics_loss_fn(pred_y, pred_q, hist_q, rain_fc, edge_index, edge_travel_times)
            
            # 4. Classification Loss (severity classes) - Vectorized
            ratio = fut_y / danger_levels.view(1, 1, -1)
            target_sev = torch.zeros_like(fut_y, dtype=torch.long, device=device)
            target_sev = torch.where(ratio >= 0.4, torch.tensor(1, device=device), target_sev)
            target_sev = torch.where(ratio >= 0.7, torch.tensor(2, device=device), target_sev)
            target_sev = torch.where(ratio >= 0.9, torch.tensor(3, device=device), target_sev)
            target_sev = torch.where(ratio >= 1.0, torch.tensor(4, device=device), target_sev)
                        
            loss_cls = criterion_ce(pred_sev_logits.view(-1, 5), target_sev.view(-1))
            
            # Combined Loss
            loss = (loss_mse_lvl + loss_mse_q) + (physics_weight * loss_phys) + (classification_weight * loss_cls)
            
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item()
            total_mse_lvl += loss_mse_lvl.item()
            total_mse_q += loss_mse_q.item()
            total_phys += loss_phys.item()
            total_cls += loss_cls.item()
            
        scheduler.step()
        
        # Validation Loop
        model.eval()
        val_nse_list = []
        with torch.no_grad():
            for batch in val_loader:
                hist_x = batch["hist_x"].to(device)
                fut_w = batch["fut_w"].to(device)
                fut_y = batch["fut_y"].to(device)
                edge_index = batch["edge_index"][0].to(device)
                edge_travel_times = batch["edge_travel_times"][0].to(device)
                
                pred_y_norm, _, _ = model(hist_x, fut_w, edge_index, edge_travel_times)
                pred_y = pred_y_norm * std_y + mean_y
                
                # Compute NSE per batch
                val_nse_list.append(calculate_nse(fut_y.flatten(), pred_y.flatten()))
                
        avg_val_nse = sum(val_nse_list) / len(val_nse_list) if val_nse_list else 0.0
        
        print(f"Epoch {epoch+1}/{epochs} | Loss: {total_loss/len(train_loader):.4f} | Level MSE: {total_mse_lvl/len(train_loader):.4f} | Phys Loss: {total_phys/len(train_loader):.4f} | Cls Loss: {total_cls/len(train_loader):.4f} | Val NSE: {avg_val_nse:.4f}")
        
        # Checkpoint if best validation NSE
        if avg_val_nse > best_nse:
            best_nse = avg_val_nse
            torch.save(model.state_dict(), os.path.join(checkpoint_dir, "best_model.pt"))
            print(f"Saved new best model checkpoint (NSE: {best_nse:.4f})")
            
    print("Model training complete.")

if __name__ == "__main__":
    train_model(epochs=5)
