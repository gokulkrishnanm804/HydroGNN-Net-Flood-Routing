import math
import torch
import torch.nn as nn

class PositionalEncoding(nn.Module):
    def __init__(self, d_model, max_len=5000):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        
        pe = pe.unsqueeze(0) # [1, max_len, d_model]
        self.register_buffer('pe', pe)

    def forward(self, x):
        """
        Args:
            x: Input tensor [Batch, Seq_Len, d_model]
        """
        return x + self.pe[:, :x.size(1)]


class TemporalTransformer(nn.Module):
    def __init__(self, hidden_dim, num_heads=4, num_layers=3, dropout=0.1):
        super().__init__()
        self.hidden_dim = hidden_dim
        
        # Positional encodings
        self.pos_encoder = PositionalEncoding(hidden_dim)
        self.pos_decoder = PositionalEncoding(hidden_dim)
        
        # Transformer Encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=num_heads,
            dim_feedforward=hidden_dim * 2,
            dropout=dropout,
            batch_first=True
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        
        # Transformer Decoder
        decoder_layer = nn.TransformerDecoderLayer(
            d_model=hidden_dim,
            nhead=num_heads,
            dim_feedforward=hidden_dim * 2,
            dropout=dropout,
            batch_first=True
        )
        self.decoder = nn.TransformerDecoder(decoder_layer, num_layers=num_layers)
        
    def forward(self, enc_input, dec_input):
        """
        Args:
            enc_input: Encoder inputs [B * N, L, hidden_dim]
            dec_input: Decoder inputs (e.g. projected forecast weather) [B * N, H, hidden_dim]
        Returns:
            dec_out: Decoder output representations [B * N, H, hidden_dim]
        """
        # Apply positional encodings
        enc_seq = self.pos_encoder(enc_input)
        dec_seq = self.pos_decoder(dec_input)
        
        # Encoder forward
        memory = self.encoder(enc_seq) # [B * N, L, hidden_dim]
        
        # Decoder forward (with causal masking for future sequence optional, 
        # but since forecast weather is fully known, we can allow full attention)
        out = self.decoder(dec_seq, memory) # [B * N, H, hidden_dim]
        
        return out
