import torch
from datasets.simulator import CONNECTIONS

def extract_spatial_attention_coefficients(model, edge_index):
    """
    Extracts attention weights from the spatial encoder's GATv2 layers.
    Returns:
        attention_map: List of dicts mapping from_station -> to_station -> weight
    """
    attention_map = []
    
    try:
        # Find the last GATv2ConvPure layer in the spatial encoder stack
        layers = model.spatial_encoder.layers
        if not layers:
            return []
            
        last_conv = layers[-1]
        
        # Ensure _alpha has been stored
        if not hasattr(last_conv, "_alpha") or last_conv._alpha is None:
            return []
            
        # alpha shape: [B * L, E_all, heads]
        alpha = last_conv._alpha
        
        # Take mean over batch * lookback and heads dimensions
        # shape: [E_all]
        mean_alpha = alpha.mean(dim=0).mean(dim=-1).cpu().numpy()
        
        # Map original edge connections (ignoring self-loops at indices >= E)
        E = edge_index.shape[1]
        
        from datasets.simulator import STATIONS
        station_ids = [s["id"] for s in STATIONS]
        
        for i in range(min(E, len(mean_alpha))):
            u = edge_index[0, i].item()
            v = edge_index[1, i].item()
            
            if u < len(station_ids) and v < len(station_ids):
                src_id = station_ids[u]
                dst_id = station_ids[v]
                attention_map.append({
                    "source": src_id,
                    "target": dst_id,
                    "weight": float(mean_alpha[i])
                })
                
    except Exception as e:
        import sys
        print(f"XAI Attention extraction failed: {str(e)}", file=sys.stderr)
        
    return attention_map
