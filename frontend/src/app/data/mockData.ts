// Mock data for HydroGNN-Net demo
export const STATIONS = [
  { id: 'BILIGUNDLU',   name: 'Biligundlu',    lat: 11.9833, lng: 77.7167, state: 'KA/TN border', river: 'Cauvery',    status: 'safe',    level: 52.3,  levelMax: 80,  flood_risk: 12, nse: 0.91, trend: 'stable'  },
  { id: 'METTUR_DAM',   name: 'Mettur Dam',    lat: 11.7833, lng: 77.8000, state: 'Tamil Nadu',   river: 'Cauvery',    status: 'alert',   level: 104.2, levelMax: 120, flood_risk: 48, nse: 0.88, trend: 'rising'  },
  { id: 'ERODE',        name: 'Erode',         lat: 11.3333, lng: 77.7167, state: 'Tamil Nadu',   river: 'Cauvery',    status: 'safe',    level: 28.1,  levelMax: 65,  flood_risk: 18, nse: 0.85, trend: 'stable'  },
  { id: 'KODUMUDI',     name: 'Kodumudi',      lat: 11.1667, lng: 77.8667, state: 'Tamil Nadu',   river: 'Cauvery',    status: 'safe',    level: 22.8,  levelMax: 50,  flood_risk: 14, nse: 0.87, trend: 'falling' },
  { id: 'KARUR',        name: 'Karur',         lat: 10.9667, lng: 78.0667, state: 'Tamil Nadu',   river: 'Amaravathi', status: 'warning', level: 38.9,  levelMax: 55,  flood_risk: 62, nse: 0.82, trend: 'rising'  },
  { id: 'MUSIRI',       name: 'Musiri',        lat: 10.9500, lng: 78.4333, state: 'Tamil Nadu',   river: 'Cauvery',    status: 'safe',    level: 19.4,  levelMax: 45,  flood_risk: 9,  nse: 0.89, trend: 'stable'  },
  { id: 'TRICHY_UPPER', name: 'Trichy Upper',  lat: 10.8000, lng: 78.7000, state: 'Tamil Nadu',   river: 'Cauvery',    status: 'danger',  level: 71.2,  levelMax: 90,  flood_risk: 78, nse: 0.86, trend: 'rising'  },
  { id: 'GRAND_ANICUT', name: 'Grand Anicut',  lat: 10.8667, lng: 79.1000, state: 'Tamil Nadu',   river: 'Cauvery',    status: 'safe',    level: 15.3,  levelMax: 35,  flood_risk: 8,  nse: 0.93, trend: 'stable'  },
];

export const RESERVOIRS = [
  { id: 'METTUR',       name: 'Mettur',         lat: 11.7833, lng: 77.8000, storage: 87420, maxStorage: 93470, inflow: 8990, outflow: 8747, level: 82.1 },
  { id: 'BHAVANISAGAR', name: 'Bhavanisagar',   lat: 11.4500, lng: 77.1500, storage: 22100, maxStorage: 32800, inflow: 1526, outflow: 1564, level: 74.4 },
  { id: 'AMARAVATHI',   name: 'Amaravathi',     lat: 10.9500, lng: 77.2000, storage: 2890,  maxStorage: 4029,  inflow: 367,  outflow: 701,  level: 59.5 },
  { id: 'HARANGI',      name: 'Harangi',        lat: 12.5000, lng: 75.8500, storage: 6100,  maxStorage: 8500,  inflow: 1692, outflow: 611,  level: 113.3 },
  { id: 'KRS',          name: 'KRS',            lat: 12.4167, lng: 76.5667, storage: 38200, maxStorage: 49452, inflow: 7278, outflow: 3297, level: 97.3 },
  { id: 'KABINI',       name: 'Kabini',         lat: 11.8000, lng: 76.3500, storage: 14800, maxStorage: 19516, inflow: 3053, outflow: 1410, level: 51.3 },
  { id: 'HEMAVATHY',    name: 'Hemavathy',      lat: 13.0500, lng: 75.9000, storage: 27800, maxStorage: 37103, inflow: 2903, outflow: 1370, level: 98.2 },
];

export const FORECAST_HORIZONS = [1, 3, 6, 12, 18, 24];

export type Status = 'safe' | 'alert' | 'warning' | 'danger' | 'critical';

export const STATUS_CONFIG: Record<string, {label: string; color: string; bg: string; shadow: string; border: string}> = {
  safe:     { label: 'Safe',     color: '#34d399', bg: 'rgba(52,211,153,0.12)',  shadow: '0 0 20px rgba(52,211,153,0.3)',  border: 'rgba(52,211,153,0.25)' },
  alert:    { label: 'Alert',    color: '#fbbf24', bg: 'rgba(251,191,36,0.12)',  shadow: '0 0 20px rgba(251,191,36,0.3)',  border: 'rgba(251,191,36,0.25)' },
  warning:  { label: 'Warning',  color: '#fb923c', bg: 'rgba(251,146,60,0.12)',  shadow: '0 0 20px rgba(251,146,60,0.3)',  border: 'rgba(251,146,60,0.25)' },
  danger:   { label: 'Danger',   color: '#fb7185', bg: 'rgba(244,63,94,0.12)',   shadow: '0 0 24px rgba(244,63,94,0.4)',   border: 'rgba(244,63,94,0.25)'  },
  critical: { label: 'Critical', color: '#a78bfa', bg: 'rgba(139,92,246,0.12)',  shadow: '0 0 28px rgba(139,92,246,0.45)', border: 'rgba(139,92,246,0.3)'  },
};

export function generateTimeSeries(stationId: string, hours = 96) {
  const base: Record<string, number> = {
    BILIGUNDLU: 52, METTUR_DAM: 104, ERODE: 28, KODUMUDI: 23,
    KARUR: 39, MUSIRI: 19, TRICHY_UPPER: 71, GRAND_ANICUT: 15,
  };
  const b = base[stationId] ?? 30;
  const now = Date.now();
  return Array.from({ length: hours }, (_, i) => {
    const t = now - (hours - i) * 3600 * 1000;
    const noise = Math.sin(i * 0.3) * 4 + Math.cos(i * 0.7) * 2;
    const surge = i > (hours * 0.75) ? (i - hours * 0.75) * 0.3 : 0;
    return {
      time: new Date(t).toISOString(),
      level:    i < (hours * 0.75) ? Math.max(0, b + noise) : null,
      forecast: i >= (hours * 0.70) ? Math.max(0, b + noise + surge) : null,
      lower:    i >= (hours * 0.70) ? Math.max(0, b + noise + surge - 2.5) : null,
      upper:    i >= (hours * 0.70) ? Math.max(0, b + noise + surge + 3.5) : null,
      label: new Date(t).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }),
    };
  });
}

export function generateRainfallSeries(days = 30) {
  return Array.from({ length: days }, (_, i) => ({
    date: `Jul ${i + 1}`,
    rainfall: Math.max(0, 15 + Math.sin(i * 0.5) * 20 + Math.random() * 30),
    avg: 22,
  }));
}

export function generateMultiStationSeries(stationIds: string[], hours = 48) {
  const base: Record<string, number> = {
    BILIGUNDLU: 52, METTUR_DAM: 104, ERODE: 28, KODUMUDI: 23,
    KARUR: 39, MUSIRI: 19, TRICHY_UPPER: 71, GRAND_ANICUT: 15,
  };
  return Array.from({ length: hours }, (_, i) => {
    const t = Date.now() - (hours - i) * 3600 * 1000;
    const row: Record<string, any> = { time: new Date(t).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) };
    stationIds.forEach(id => { row[id] = Math.max(0, (base[id] ?? 30) + Math.sin(i * 0.3 + id.length * 0.4) * 5 + Math.cos(i * 0.7) * 2); });
    return row;
  });
}

export const MODEL_METRICS = {
  nse: 0.891, kge: 0.873, rmse: 0.42, mae: 0.31, pbias: -1.2,
  csi: 0.78, pod: 0.84, far: 0.12, accuracy: 0.88,
  training_epochs: 178, best_epoch: 163, total_params: 2_847_392,
};

export const PIPELINE_STATUS = [
  { name: 'ERA5 Reanalysis',    status: 'complete',  pct: 100, files: 8,   size: '33 MB' },
  { name: 'IMD Rainfall',       status: 'complete',  pct: 100, files: 6,   size: '146 MB' },
  { name: 'Reservoir Ops',      status: 'complete',  pct: 100, files: 1,   size: '2.7 MB' },
  { name: 'CWC River Gauge',    status: 'partial',   pct: 72,  files: 2,   size: '135 MB' },
  { name: 'HydroRIVERS',        status: 'complete',  pct: 100, files: 6,   size: '449 MB' },
  { name: 'SRTM DEM',           status: 'complete',  pct: 100, files: 8,   size: '1.24 GB' },
  { name: 'GPM IMERG',          status: 'retired',   pct: 0,   files: 0,   size: '—' },
  { name: 'PyG Dataset',        status: 'pending',   pct: 0,   files: 0,   size: '—' },
];
