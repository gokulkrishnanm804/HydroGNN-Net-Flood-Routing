'use client';

const API_BASE = 'http://localhost:8000';
let tokenCache: string | null = null;

// Helper to retrieve auth token
async function getAuthToken(): Promise<string> {
  if (tokenCache) return tokenCache;

  // Attempt login with control room demo credentials
  try {
    const res = await fetch(`${API_BASE}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: 'admin@hydrognn.in',
        password: 'hydrognn2026',
      }),
    });

    if (!res.ok) {
      throw new Error(`Login failed with status ${res.status}`);
    }

    const data = await res.json();
    tokenCache = data.access_token;
    return tokenCache || '';
  } catch (err) {
    console.error('API service authentication error:', err);
    throw err;
  }
}

// Generates headers with token, retrying login once if request returns 401
async function fetchWithAuth(url: string, options: RequestInit = {}): Promise<any> {
  const token = await getAuthToken();
  const headers = {
    ...options.headers,
    'Authorization': `Bearer ${token}`,
  };

  let res = await fetch(url, { ...options, headers });

  if (res.status === 401) {
    // Clear token cache and retry login once
    tokenCache = null;
    const newToken = await getAuthToken();
    const retryHeaders = {
      ...options.headers,
      'Authorization': `Bearer ${newToken}`,
    };
    res = await fetch(url, { ...options, headers: retryHeaders });
  }

  if (!res.ok) {
    throw new Error(`Request to ${url} failed with status ${res.status}`);
  }

  return res.json();
}

export const api = {
  // Authentication
  async login(): Promise<string> {
    return getAuthToken();
  },

  // Health
  async getHealth(): Promise<{ status: string; model_status: string }> {
    const res = await fetch(`${API_BASE}/api/health`);
    if (!res.ok) throw new Error('Health check failed');
    return res.json();
  },

  // Dashboard
  async getDashboard(): Promise<{
    timestamp: string;
    active_warnings: number;
    average_reservoir_fill_pct: number;
    heavy_rain_stations_count: number;
    stations: any[];
    reservoirs: any[];
    decision_support: string;
  }> {
    return fetchWithAuth(`${API_BASE}/api/dashboard`);
  },

  // Predict convolved hydrographs
  async getPrediction(stationId: string, horizonsHours: number[] = [6, 12, 24]): Promise<{
    station_id: string;
    predictions: any[];
    hydrograph: any[];
    rain_overlay: any[];
    discharge_overlay: any[];
    upstream_sources: any[];
    routing_metadata: any;
    danger_level_m: number;
    warning_level_m: number;
    safe_level_m: number;
    xai_attributions: Record<string, number>;
    gat_attention: any[];
  }> {
    return fetchWithAuth(`${API_BASE}/api/predict`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        station_id: stationId,
        horizons_hours: horizonsHours,
      }),
    });
  },

  // Alerts Warning Log
  async getAlerts(): Promise<any[]> {
    return fetchWithAuth(`${API_BASE}/api/alerts`);
  },

  async getHistoricalAlerts(): Promise<any[]> {
    return fetchWithAuth(`${API_BASE}/api/alerts/history`);
  },

  // Chatbot Assistant
  async queryChat(message: string): Promise<{ query: string; response: string }> {
    return fetchWithAuth(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    });
  },

  // Satellite Catalog Metadata
  async getSatellite(): Promise<{
    status: string;
    message: string;
    scenes: any[];
    total_scenes: number;
    source: string;
  }> {
    return fetchWithAuth(`${API_BASE}/api/satellite`);
  },

  // Monitoring Diagnostics
  async getDiagnostics(): Promise<{
    status: string;
    api_latency_ms: number;
    database_health: string;
    scheduler_status: string;
    data_drift: string;
    model_drift: string;
    system_metrics: { cpu_usage_pct: number; memory_usage_pct: number };
    inference_latency_avg_ms: number;
    prediction_count: number;
    last_updated: string;
  }> {
    const res = await fetch(`${API_BASE}/api/monitoring/diagnostics`);
    if (!res.ok) throw new Error('Diagnostics check failed');
    return res.json();
  },

  // Replays
  async getReplayEvents(): Promise<any[]> {
    const res = await fetch(`${API_BASE}/api/replay/events`);
    if (!res.ok) throw new Error('Replay events query failed');
    return res.json();
  },

  async triggerReplay(eventName: string, stationId: string): Promise<{
    event_name: string;
    station_id: string;
    simulation_steps_count: number;
    comparison_timeline: any[];
  }> {
    const res = await fetch(`${API_BASE}/api/replay/trigger`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event_name: eventName, station_id: stationId }),
    });
    if (!res.ok) throw new Error('Replay trigger failed');
    return res.json();
  },
};
