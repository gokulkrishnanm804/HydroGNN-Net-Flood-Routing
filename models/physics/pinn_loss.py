import torch
import torch.nn as nn

class PhysicsInformedLoss(nn.Module):
    def __init__(self, step_minutes=15):
        super().__init__()
        self.step_minutes = step_minutes
        self.steps_per_hour = 60 // step_minutes
        
    def forward(self, pred_level, pred_q, hist_q, rain, edge_index, edge_travel_times):
        """
        Computes continuity equation loss (Saint-Venant continuity).
        Args:
            pred_level: Predicted future levels [B, H, N]
            pred_q: Predicted future discharge [B, H, N]
            hist_q: Historical observed discharge [B, L, N]
            rain: Future rainfall forecast [B, H, N]
            edge_index: Adjacency list [2, E]
            edge_travel_times: Travel times [E]
        Returns:
            loss: Mean squared physics conservation violation
        """
        B, H, N = pred_q.shape
        L = hist_q.shape[1]
        device = pred_q.device
        
        src, dst = edge_index[0], edge_index[1]
        E = edge_index.shape[1]
        
        # Calculate lag steps for each edge
        lag_steps = (edge_travel_times * self.steps_per_hour).round().long()
        
        loss_val = torch.tensor(0.0, device=device)
        count = 0
        
        # We check conservation for each future step h in 0..H-1
        for h in range(1, H):
            # Compute rate of change of storage (or level as proxy) at downstream nodes: dS/dt
            # Shape: [B, N]
            d_level = pred_level[:, h, :] - pred_level[:, h-1, :]
            
            # Sum incoming routed discharge for each node
            # Shape: [B, N]
            incoming_q = torch.zeros(B, N, device=device)
            
            for e in range(E):
                u, v = src[e].item(), dst[e].item()
                lag = lag_steps[e].item()
                
                # Retrieve discharge from node u (upstream) at time (h - lag)
                if h - lag >= 0:
                    q_val = pred_q[:, h - lag, u]
                else:
                    # Look back into history
                    hist_idx = L + (h - lag)
                    if hist_idx >= 0 and hist_idx < L:
                        q_val = hist_q[:, hist_idx, u]
                    else:
                        q_val = hist_q[:, 0, u] # fallback
                        
                incoming_q[:, v] = incoming_q[:, v] + q_val
                
            # Outgoing flow at each node is its own discharge
            outgoing_q = pred_q[:, h, :]
            
            # Local rainfall runoff (lateral inflow)
            # rain is forecast [B, H, N]
            lateral_inflow = rain[:, h, :] * 5.0 # scale factor
            
            # Continuity violation: dLevel - (Inflow - Outflow + Lateral) * dt
            # Level change should be proportional to mass balance
            # For simplicity, we model LevelChange ~ Inflow - Outflow + LateralInflow
            # Normalize scale by dividing Q by 100
            expected_change = (incoming_q - outgoing_q + lateral_inflow) * 0.05
            
            violation = d_level - expected_change
            loss_val = loss_val + torch.mean(violation ** 2)
            count += 1
            
        return loss_val / max(count, 1)
