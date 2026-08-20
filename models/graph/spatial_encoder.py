import torch
import torch.nn as nn
import torch.nn.functional as F

class GATv2ConvPure(nn.Module):
    def __init__(self, in_channels, out_channels, heads=4, edge_dim=1, dropout=0.1):
        super().__init__()
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.heads = heads
        self.edge_dim = edge_dim
        
        # Output channels must be divisible by heads
        assert out_channels % heads == 0, "out_channels must be divisible by heads"
        self.head_dim = out_channels // heads
        
        # Projections
        self.lin_src = nn.Linear(in_channels, out_channels, bias=False)
        self.lin_dst = nn.Linear(in_channels, out_channels, bias=False)
        self.lin_edge = nn.Linear(edge_dim, out_channels, bias=False)
        
        # Attention weight vector
        self.attn_linear = nn.Linear(self.head_dim, 1, bias=False)
        
        # Value projection
        self.lin_val = nn.Linear(in_channels, out_channels, bias=False)
        
        # Dropout
        self.dropout = nn.Dropout(dropout)
        
    def forward(self, x, edge_index, edge_attr=None):
        """
        Args:
            x: Node features [B, N, in_channels]
            edge_index: Adjacency list [2, E]
            edge_attr: Edge features [E, edge_dim]
        Returns:
            out: Aggregated embeddings [B, N, out_channels]
        """
        B, N, C = x.shape
        E = edge_index.shape[1]
        
        # Add self-loops to ensure every node aggregates itself
        # edge_index: [2, E]
        self_loop_indices = torch.arange(N, device=x.device).unsqueeze(0).repeat(2, 1)
        edge_index_all = torch.cat([edge_index, self_loop_indices], dim=1) # [2, E + N]
        
        src, dst = edge_index_all[0], edge_index_all[1]
        E_all = edge_index_all.shape[1]
        
        # Get edge attributes for self-loops
        if edge_attr is not None:
            # Self loops get 0 travel time or neutral edge attributes
            self_loop_attr = torch.zeros(N, self.edge_dim, device=x.device)
            edge_attr_all = torch.cat([edge_attr, self_loop_attr], dim=0) # [E + N, edge_dim]
        else:
            edge_attr_all = torch.zeros(E_all, self.edge_dim, device=x.device)
            
        # 1. Project node representations
        # Shape: [B, N, out_channels]
        x_src_proj = self.lin_src(x)
        x_dst_proj = self.lin_dst(x)
        
        # 2. Extract edge-level node embeddings
        # Shape: [B, E_all, out_channels]
        h_src = x_src_proj[:, src, :]
        h_dst = x_dst_proj[:, dst, :]
        
        # 3. Add edge features
        h_edge = self.lin_edge(edge_attr_all).unsqueeze(0) # [1, E_all, out_channels]
        
        # Combined projected features
        # Shape: [B, E_all, out_channels]
        feats = h_src + h_dst + h_edge
        
        # Reshape for multi-head attention: [B, E_all, heads, head_dim]
        feats = feats.view(B, E_all, self.heads, self.head_dim)
        
        # 4. Compute attention scores: LeakyReLU and linear projection
        # Shape: [B, E_all, heads]
        attn_scores = self.attn_linear(F.leaky_relu(feats)).squeeze(-1)
        
        # 5. Softmax over targets
        # Exponentiate and avoid overflow
        max_scores = attn_scores.max(dim=1, keepdim=True)[0]
        exp_scores = torch.exp(attn_scores - max_scores) # [B, E_all, heads]
        
        # Sum exponentiated scores per target node
        # We scatter add exp_scores into [B, N, heads]
        sum_exp = torch.zeros(B, N, self.heads, device=x.device)
        dst_expanded = dst.unsqueeze(0).unsqueeze(-1).expand(B, -1, self.heads) # [B, E_all, heads]
        sum_exp.scatter_add_(1, dst_expanded, exp_scores)
        
        # Gather sum_exp back to edges to normalize
        sum_exp_for_edges = torch.gather(sum_exp, 1, dst_expanded) # [B, E_all, heads]
        alpha = exp_scores / (sum_exp_for_edges + 1e-8) # [B, E_all, heads]
        alpha = self.dropout(alpha)
        self._alpha = alpha.detach()
        
        # 6. Aggregate value features
        # Shape: [B, N, out_channels]
        val_proj = self.lin_val(x)
        
        # Shape: [B, E_all, out_channels]
        h_val = val_proj[:, src, :]
        # Reshape for heads: [B, E_all, heads, head_dim]
        h_val = h_val.view(B, E_all, self.heads, self.head_dim)
        
        # Multiply by attention weights: [B, E_all, heads, head_dim]
        weighted_val = h_val * alpha.unsqueeze(-1)
        
        # Scatter add aggregated outputs to target nodes
        # Shape: [B, N, heads, head_dim]
        out_heads = torch.zeros(B, N, self.heads, self.head_dim, device=x.device)
        dst_expanded_out = dst_expanded.unsqueeze(-1).expand(-1, -1, -1, self.head_dim) # [B, E_all, heads, head_dim]
        out_heads.scatter_add_(1, dst_expanded_out, weighted_val)
        
        # Concatenate heads output back to [B, N, out_channels]
        out = out_heads.view(B, N, self.out_channels)
        return out


class SpatialEncoder(nn.Module):
    def __init__(self, in_dim, hidden_dim, heads=4, num_layers=3, edge_dim=1, dropout=0.1):
        super().__init__()
        self.layers = nn.ModuleList()
        self.norms = nn.ModuleList()
        
        dims = [in_dim] + [hidden_dim] * num_layers
        for l in range(num_layers):
            self.layers.append(
                GATv2ConvPure(
                    in_channels=dims[l],
                    out_channels=dims[l+1],
                    heads=heads,
                    edge_dim=edge_dim,
                    dropout=dropout
                )
            )
            self.norms.append(nn.LayerNorm(dims[l+1]))
            
    def forward(self, x, edge_index, edge_attr=None):
        """
        Args:
            x: Node features [B, N, in_dim]
            edge_index: Adjacency list [2, E]
            edge_attr: Edge features [E, edge_dim]
        Returns:
            Embeddings: [B, N, hidden_dim]
        """
        h = x
        for conv, norm in zip(self.layers, self.norms):
            # GAT Conv
            h_new = conv(h, edge_index, edge_attr)
            # Residual connection if dimensions match
            if h.shape[-1] == h_new.shape[-1]:
                h = norm(F.relu(h_new) + h)
            else:
                h = norm(F.relu(h_new))
        return h
