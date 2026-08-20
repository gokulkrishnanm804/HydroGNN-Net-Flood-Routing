const API_BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";

const getHeaders = () => {
  const token = localStorage.getItem("hydrognn_token");
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
};

export const api = {
  async login(email, password) {
    const res = await fetch(`${API_BASE_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Authentication Failed");
    }
    const data = await res.json();
    localStorage.setItem("hydrognn_token", data.access_token);
    return data;
  },

  logout() {
    localStorage.removeItem("hydrognn_token");
  },

  isAuthenticated() {
    return !!localStorage.getItem("hydrognn_token");
  },

  async getDashboard() {
    const res = await fetch(`${API_BASE_URL}/dashboard`, {
      method: "GET",
      headers: getHeaders(),
    });
    if (!res.ok) {
      if (res.status === 401) this.logout();
      throw new Error("Failed to fetch dashboard summary");
    }
    return res.json();
  },

  async getPrediction(stationId, horizons = [1, 3, 6, 12, 18, 24], compareStations = []) {
    const body = {
      station_id: stationId,
      horizons_hours: horizons,
    };
    if (compareStations && compareStations.length > 0) {
      body.compare_stations = compareStations;
    }
    const res = await fetch(`${API_BASE_URL}/predict`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      let detail = "Failed to fetch model prediction data";
      try { const e = await res.json(); detail = e.detail || detail; } catch {}
      throw new Error(detail);
    }
    return res.json();
  },

  async getAlerts() {
    const res = await fetch(`${API_BASE_URL}/alerts`, {
      method: "GET",
      headers: getHeaders(),
    });
    if (!res.ok) {
      throw new Error("Failed to fetch active alerts");
    }
    return res.json();
  },

  async sendChatMessage(message) {
    const res = await fetch(`${API_BASE_URL}/chat`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({ message }),
    });
    if (!res.ok) {
      throw new Error("Chat assistant request failed");
    }
    return res.json();
  },

  async getSatellite() {
    const res = await fetch(`${API_BASE_URL}/satellite`, {
      method: "GET",
      headers: getHeaders(),
    });
    if (!res.ok) {
      throw new Error("Failed to fetch satellite data");
    }
    return res.json();
  },

  // ── Priority 1: Monitoring diagnostics ────────────────────────────────────
  async getMonitoring() {
    const res = await fetch(`${API_BASE_URL}/monitoring/diagnostics`, {
      method: "GET",
      headers: getHeaders(),
    });
    if (!res.ok) {
      throw new Error("Failed to fetch monitoring diagnostics");
    }
    return res.json();
  },

  // ── Priority 2: Replay ────────────────────────────────────────────────────
  async getReplayEvents() {
    const res = await fetch(`${API_BASE_URL}/replay/events`, {
      method: "GET",
      headers: getHeaders(),
    });
    if (!res.ok) {
      throw new Error("Failed to fetch replay events");
    }
    return res.json();
  },

  async triggerReplay(eventName, stationId) {
    const res = await fetch(`${API_BASE_URL}/replay/trigger`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({ event_name: eventName, station_id: stationId }),
    });
    if (!res.ok) {
      throw new Error("Failed to trigger replay simulation");
    }
    return res.json();
  },
};
