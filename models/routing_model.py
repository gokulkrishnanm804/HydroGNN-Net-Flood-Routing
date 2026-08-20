import torch
import torch.nn as nn
import torch.nn.functional as F
from models.graph.spatial_encoder import SpatialEncoder
from models.transformer.temporal_transformer import TemporalTransformer

class HydroGNNNet(nn.Module):
    def __init__(self, node_in_dim=8, weather_in_dim=3, hidden_dim=64, heads=4, num_layers=3, dropout=0.1):
        super().__init__()
        self.hidden_dim = hidden_dim
        
        # Spatial Encoder (GATv2 stack)
        # Edge attribute dimension is 1 (travel time)
        self.spatial_encoder = SpatialEncoder(
            in_dim=node_in_dim,
            hidden_dim=hidden_dim,
            heads=heads,
            num_layers=num_layers,
            edge_dim=1,
            dropout=dropout
        )
        
        # Weather forecast projection for Decoder input
        self.weather_proj = nn.Linear(weather_in_dim, hidden_dim)
        
        # Temporal Transformer Encoder-Decoder
        self.temporal_transformer = TemporalTransformer(
            hidden_dim=hidden_dim,
            num_heads=heads,
            num_layers=num_layers,
            dropout=dropout
        )
        
        # Prediction Heads
        # 1. Water Level Regression Head
        self.level_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 2, 1)
        )
        
        # 2. Discharge Regression Head
        self.discharge_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 2, 1)
        )
        
        # 3. Severity Classification Head (5 classes: Safe, Low, Moderate, High, Severe)
        self.severity_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 2, 5)
        )
        
        # 4. Flood Arrival Time Regression Head (hours)
        self.arrival_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 2, 1)
        )
        
        # Learned logs of task variances for multi-task loss weighting
        self.log_vars = nn.Parameter(torch.zeros(5))
        
    def forward(self, hist_x, fut_w, edge_index, edge_travel_times):
        """
        Args:
            hist_x: Historical node features [B, L, N, node_in_dim]
            fut_w: Future forecast weather [B, H, N, weather_in_dim]
            edge_index: Adjacency list [2, E]
            edge_travel_times: Travel times [E]
        Returns:
            pred_level: Predicted future water levels [B, H, N]
            pred_q: Predicted future discharge [B, H, N]
            pred_sev: Predicted future severity class logits [B, H, N, 5]
            pred_arrival: Predicted future flood wave arrival times [B, H, N]
        """
        B, L, N, C = hist_x.shape
        H = fut_w.shape[1]
        
        # 1. Spatial Learning over each lookback timestep
        hist_x_flat = hist_x.view(B * L, N, C)
        spatial_emb_flat = self.spatial_encoder(hist_x_flat, edge_index, edge_travel_times.unsqueeze(-1))
        spatial_emb = spatial_emb_flat.view(B, L, N, self.hidden_dim)
        
        # 2. Reshape for Temporal sequence-to-sequence model: [B * N, L, hidden_dim]
        enc_input = spatial_emb.permute(0, 2, 1, 3).reshape(B * N, L, self.hidden_dim)
        
        # 3. Prepare Decoder inputs (Future weather forecasts)
        fut_w_flat = fut_w.permute(0, 2, 1, 3).reshape(B * N, H, -1)
        dec_input = self.weather_proj(fut_w_flat)
        
        # 4. Spatio-Temporal Fusion
        transformer_out = self.temporal_transformer(enc_input, dec_input)
        fused_emb = transformer_out.view(B, N, H, self.hidden_dim).permute(0, 2, 1, 3)
        
        # 5. Apply task heads
        pred_level = self.level_head(fused_emb).squeeze(-1)
        pred_q = self.discharge_head(fused_emb).squeeze(-1)
        pred_sev = self.severity_head(fused_emb)
        pred_arrival = self.arrival_head(fused_emb).squeeze(-1)
        
        return pred_level, pred_q, pred_sev, pred_arrival
        
    def compute_multitask_loss(self, pred_level, target_level, pred_q, target_q, pred_sev, target_sev, pred_arrival, target_arrival, physics_loss=0.0):
        """
        Balances dynamic task learning objective using trainable uncertainty variables.
        """
        loss_level = F.mse_loss(pred_level, target_level)
        loss_q = F.mse_loss(pred_q, target_q)
        loss_sev = F.cross_entropy(pred_sev.view(-1, 5), target_sev.view(-1).long())
        loss_arrival = F.smooth_l1_loss(pred_arrival, target_arrival)
        
        # Uncertainty weights
        w_lvl = torch.exp(-self.log_vars[0])
        w_q = torch.exp(-self.log_vars[1])
        w_sev = torch.exp(-self.log_vars[2])
        w_arr = torch.exp(-self.log_vars[3])
        w_phy = torch.exp(-self.log_vars[4])
        
        loss_total = (
            w_lvl * loss_level + 
            w_q * loss_q + 
            w_sev * loss_sev + 
            w_arr * loss_arrival + 
            w_phy * physics_loss + 
            self.log_vars.sum()
        )
        return loss_total, {
            "level": loss_level.item(),
            "discharge": loss_q.item(),
            "severity": loss_sev.item(),
            "arrival": loss_arrival.item()
        }
         
    def predict_with_uncertainty(self, hist_x, fut_w, edge_index, edge_travel_times, num_samples=10):
        """
        Uses MC Dropout to generate multiple stochastic predictions and compute uncertainty.
        """
        self.train() # Enable dropout layer active at inference
        
        levels = []
        discharges = []
        severs = []
        arrivals = []
        
        with torch.no_grad():
            for _ in range(num_samples):
                lvl, q, sev, arr = self.forward(hist_x, fut_w, edge_index, edge_travel_times)
                levels.append(lvl.unsqueeze(0))
                discharges.append(q.unsqueeze(0))
                severs.append(F.softmax(sev, dim=-1).unsqueeze(0))
                arrivals.append(arr.unsqueeze(0))
                
        # [num_samples, B, H, N]
        levels = torch.cat(levels, dim=0)
        discharges = torch.cat(discharges, dim=0)
        severs = torch.cat(severs, dim=0)
        arrivals = torch.cat(arrivals, dim=0)
        
        mean_level = levels.mean(dim=0)
        std_level = levels.std(dim=0)
        
        mean_q = discharges.mean(dim=0)
        std_q = discharges.std(dim=0)
        
        mean_sev = severs.mean(dim=0)
        
        mean_arrival = arrivals.mean(dim=0)
        std_arrival = arrivals.std(dim=0)
        
        return mean_level, std_level, mean_q, std_q, mean_sev, mean_arrival, std_arrival
