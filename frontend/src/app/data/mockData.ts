// Cauvery River Basin Canonical Network Station Reference
export interface StationRef {
  id: string;
  name: string;
  lat: number;
  lng: number;
  river: string;
  state: string;
  type: 'gauge' | 'reservoir';
}

export const CAUVERY_STATIONS: StationRef[] = [
  { id: 'BILIGUNDLU', name: 'Biligundlu', lat: 11.9833, lng: 77.7167, state: 'KA/TN Border', river: 'Cauvery', type: 'gauge' },
  { id: 'METTUR_DAM', name: 'Mettur Dam', lat: 11.7833, lng: 77.8000, state: 'Tamil Nadu', river: 'Cauvery', type: 'reservoir' },
  { id: 'ERODE', name: 'Erode', lat: 11.3333, lng: 77.7167, state: 'Tamil Nadu', river: 'Cauvery', type: 'gauge' },
  { id: 'KODUMUDI', name: 'Kodumudi', lat: 11.1667, lng: 77.8667, state: 'Tamil Nadu', river: 'Cauvery', type: 'gauge' },
  { id: 'KARUR', name: 'Karur', lat: 10.9667, lng: 78.0667, state: 'Tamil Nadu', river: 'Amaravathi', type: 'gauge' },
  { id: 'MUSIRI', name: 'Musiri', lat: 10.9500, lng: 78.4333, state: 'Tamil Nadu', river: 'Cauvery', type: 'gauge' },
  { id: 'TRICHY_UPPER', name: 'Trichy Upper', lat: 10.8000, lng: 78.7000, state: 'Tamil Nadu', river: 'Cauvery', type: 'gauge' },
  { id: 'GRAND_ANICUT', name: 'Grand Anicut', lat: 10.8667, lng: 79.1000, state: 'Tamil Nadu', river: 'Cauvery', type: 'gauge' },
];

export const CAUVERY_RESERVOIRS = [
  { id: 'METTUR', name: 'Mettur Dam', lat: 11.7833, lng: 77.8000, capacity_mcft: 93470 },
  { id: 'BHAVANISAGAR', name: 'Bhavanisagar', lat: 11.4500, lng: 77.1500, capacity_mcft: 32800 },
  { id: 'AMARAVATHI', name: 'Amaravathi', lat: 10.9500, lng: 77.2000, capacity_mcft: 4029 },
  { id: 'HARANGI', name: 'Harangi', lat: 12.5000, lng: 75.8500, capacity_mcft: 8500 },
  { id: 'KRS', name: 'KRS (Krishna Raja Sagara)', lat: 12.4167, lng: 76.5667, capacity_mcft: 49452 },
  { id: 'KABINI', name: 'Kabini', lat: 11.8000, lng: 76.3500, capacity_mcft: 19516 },
  { id: 'HEMAVATHY', name: 'Hemavathy', lat: 13.0500, lng: 75.9000, capacity_mcft: 37103 },
];

// Verified HydroGNN-Net Experiment 9 Evaluation Specifications
export const EXPERIMENT_9_SPECS = {
  experiment_id: 'Experiment 9',
  architecture: 'GRU + GATv2 + GraphSAGE + Stage Proj + Gating Head',
  checkpoint: 'Models/best_model.pt',
  total_parameters: 72594,
  historical_input_hours: 24,
  native_forecast_horizons: [6, 12, 24],
  evaluation_protocol: 'Held-out Test Evaluation',
  node_features: 7,
  edge_features: 3,
  hidden_dimension: 64,
  gru_layers: 2,
  gatv2_layers: 2,
  gat_heads: 4,
  graphsage_hidden: 64,
  dropout: 0.2,
  metrics: {
    test_nse: 0.9968,
    test_rmse_m: 0.4974,
    test_mae_m: 0.1786,
  },
};
