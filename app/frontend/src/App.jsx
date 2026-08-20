import React, { useState, useEffect, useRef } from 'react';
import { 
  MapContainer, 
  TileLayer, 
  CircleMarker, 
  Popup 
} from 'react-leaflet';
import { 
  Activity, 
  AlertTriangle, 
  Droplet, 
  MapPin, 
  MessageSquare, 
  Send, 
  ShieldAlert, 
  Wind, 
  LogIn, 
  LogOut, 
  Compass, 
  Database, 
  Cpu,
  ChevronRight,
  GitCompare,
  X
} from 'lucide-react';
import { api } from './services/api';
import HydroChart from './components/HydroChart';

// Custom Map center for Tamil Nadu
const TN_CENTER = [10.8, 78.5];

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(api.isAuthenticated());
  // Credentials: do NOT pre-fill — user must type them in
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");

  // Dashboard states
  const [dashboardData, setDashboardData] = useState(null);
  const [activeTab, setActiveTab] = useState("map");
  const [selectedStationId, setSelectedStationId] = useState("METTUR");
  const [predictionData, setPredictionData] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [loadingPred, setLoadingPred] = useState(false);
  const [loadingDash, setLoadingDash] = useState(true);
  const [lastRefreshed, setLastRefreshed] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  // Issue #5: visible error state for backend connectivity
  const [backendError, setBackendError] = useState(null);

  // Refs for interval timers — prevents duplicate requests and memory leaks
  const dashIntervalRef = useRef(null);
  const alertsIntervalRef = useRef(null);
  // Ref to guard in-flight fetch (prevents duplicate concurrent requests)
  const fetchingDashRef = useRef(false);
  const fetchingAlertsRef = useRef(false);

  // Chatbot states
  const [chatMessage, setChatMessage] = useState("");
  const [chatHistory, setChatHistory] = useState([
    { sender: "bot", text: "Hello! I am the HydroGNN-Net Decision Support Assistant. I monitor Cauvery, Bhavani, Vaigai, and other Tamil Nadu basins. Ask me about reservoir capacities, active alerts, or predictions." }
  ]);
  const [sendingChat, setSendingChat] = useState(false);
  const chatEndRef = useRef(null);

  // Satellite imagery state
  const [satelliteData, setSatelliteData] = useState(null);

  // Priority 1: Monitoring diagnostics state
  const [monitoringData, setMonitoringData] = useState(null);
  const monitoringIntervalRef = useRef(null);

  // Priority 2: Replay state
  const [replayEvents, setReplayEvents] = useState([]);
  const [activeReplayEvent, setActiveReplayEvent] = useState(null);
  const [replayResult, setReplayResult] = useState(null);
  const [replayLoading, setReplayLoading] = useState(false);

  // Phase 9: Multi-station comparison (up to 4 stations)
  const [compareStations, setCompareStations] = useState([]);
  const [compareData, setCompareData]     = useState([]);
  const [showComparePanel, setShowComparePanel] = useState(false);

  // Ref to always capture latest selectedStationId inside the 60s interval closure
  const selectedStationIdRef = useRef(selectedStationId);
  useEffect(() => {
    selectedStationIdRef.current = selectedStationId;
  }, [selectedStationId]);

  // ── Auto-refresh setup ──────────────────────────────────────────────────────
  // On login: immediate fetch + set up 60s polling intervals
  useEffect(() => {
    if (!isAuthenticated) return;

    fetchDashboard();
    fetchAlerts();
    fetchSatellite();  // Initial satellite load on login
    fetchMonitoring(); // Priority 1: load monitoring on login
    fetchReplayEvents(); // Priority 2: load replay events on login

    // Dashboard auto-refresh every 60 seconds
    dashIntervalRef.current = setInterval(() => {
      fetchDashboard();
    }, 60_000);

    // Alerts auto-refresh every 60 seconds
    alertsIntervalRef.current = setInterval(() => {
      fetchAlerts();
    }, 60_000);

    // FIX B7: Prediction auto-refresh every 60 seconds (was missing — hydrograph went stale)
    const predInterval = setInterval(() => {
      if (selectedStationIdRef.current) {
        fetchPrediction(selectedStationIdRef.current);
      }
    }, 60_000);

    // Satellite data changes daily — poll every 5 minutes
    const satInterval = setInterval(() => {
      fetchSatellite();
    }, 300_000);

    // Priority 1: Monitoring auto-refresh every 60 seconds
    monitoringIntervalRef.current = setInterval(() => {
      fetchMonitoring();
    }, 60_000);

    // Cleanup on logout or unmount
    return () => {
      clearInterval(dashIntervalRef.current);
      clearInterval(alertsIntervalRef.current);
      clearInterval(predInterval);
      clearInterval(satInterval);
      clearInterval(monitoringIntervalRef.current);
      dashIntervalRef.current = null;
      alertsIntervalRef.current = null;
      monitoringIntervalRef.current = null;
    };
  }, [isAuthenticated]);

  // Re-fetch prediction immediately when station changes
  useEffect(() => {
    if (isAuthenticated && selectedStationId) {
      fetchPrediction(selectedStationId);
    }
  }, [selectedStationId, isAuthenticated]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory]);

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoginError("");
    try {
      await api.login(email, password);
      setIsAuthenticated(true);
    } catch (err) {
      setLoginError(err.message);
    }
  };

  const handleLogout = () => {
    api.logout();
    setIsAuthenticated(false);
  };

  const fetchDashboard = async () => {
    // Guard: skip if a fetch is already in flight
    if (fetchingDashRef.current) return;
    fetchingDashRef.current = true;
    setRefreshing(true);
    try {
      const data = await api.getDashboard();
      setDashboardData(data);
      setLastRefreshed(new Date());
      setBackendError(null); // clear any prior error on success
    } catch (err) {
      console.error("Dashboard fetch failed:", err);
      // Issue #5: surface error visibly — users should not see a silent blank screen
      setBackendError(`Backend unreachable: ${err.message || 'Network error'}. Retrying in 60s.`);
    } finally {
      fetchingDashRef.current = false;
      setRefreshing(false);
      setLoadingDash(false);
    }
  };

  const fetchAlerts = async () => {
    if (fetchingAlertsRef.current) return;
    fetchingAlertsRef.current = true;
    try {
      const data = await api.getAlerts();
      setAlerts(data);
    } catch (err) {
      console.error("Alerts fetch failed:", err);
      // Don't overwrite a dashboard error with an alerts error — just log it
    } finally {
      fetchingAlertsRef.current = false;
    }
  };

  const fetchPrediction = async (stationId) => {
    try {
      setLoadingPred(true);
      const data = await api.getPrediction(stationId, [1, 3, 6, 12, 18, 24]);
      setPredictionData(data);

      // Phase 9: fetch compare station data in parallel
      if (compareStations.length > 0) {
        const cmpResults = await Promise.allSettled(
          compareStations.map(cid => api.getPrediction(cid, [1, 3, 6, 12, 18, 24]))
        );
        const cmpData = cmpResults
          .map((r, i) => ({
            stationId: compareStations[i],
            stationName: compareStations[i],
            predictionData: r.status === 'fulfilled' ? r.value : null,
          }))
          .filter(c => c.predictionData !== null);
        setCompareData(cmpData);
      }
    } catch (err) {
      console.error("Prediction fetch failed:", err);
      if (!dashboardData) {
        setBackendError(`Prediction endpoint unreachable: ${err.message || 'Network error'}`);
      }
    } finally {
      setLoadingPred(false);
    }
  };

  const fetchSatellite = async () => {
    try {
      const data = await api.getSatellite();
      setSatelliteData(data);
    } catch (err) {
      console.error("Satellite fetch failed:", err);
      // Non-critical — don't surface to backendError
    }
  };

  // Priority 1: Monitoring fetch
  const fetchMonitoring = async () => {
    try {
      const data = await api.getMonitoring();
      setMonitoringData(data);
    } catch (err) {
      console.error("Monitoring fetch failed:", err);
    }
  };

  // Priority 2: Replay events fetch
  const fetchReplayEvents = async () => {
    try {
      const data = await api.getReplayEvents();
      setReplayEvents(data);
      if (data.length > 0 && !activeReplayEvent) {
        setActiveReplayEvent(data[0].name);
      }
    } catch (err) {
      console.error("Replay events fetch failed:", err);
    }
  };

  // Priority 2: Trigger a replay simulation
  const fetchReplay = async (eventName, stationId) => {
    if (!eventName || !stationId) return;
    setReplayLoading(true);
    setReplayResult(null);
    try {
      const data = await api.triggerReplay(eventName, stationId);
      setReplayResult(data);
    } catch (err) {
      console.error("Replay trigger failed:", err);
    } finally {
      setReplayLoading(false);
    }
  };

  const handleSendChat = async (e) => {
    e.preventDefault();
    if (!chatMessage.trim()) return;
    
    const userMsg = chatMessage;
    setChatHistory(prev => [...prev, { sender: "user", text: userMsg }]);
    setChatMessage("");
    setSendingChat(true);
    
    try {
      const res = await api.sendChatMessage(userMsg);
      setChatHistory(prev => [...prev, { sender: "bot", text: res.response }]);
    } catch (err) {
      setChatHistory(prev => [...prev, { sender: "bot", text: "Error: Failed to reach assistant. Please verify the backend is running." }]);
    } finally {
      setSendingChat(false);
    }
  };

  const getSeverityColor = (risk) => {
    switch (risk) {
      case "Safe": return "#10b981";       // Emerald
      case "Low Risk": return "#eab308";   // Amber
      case "Moderate Risk": return "#f97316"; // Orange
      case "High Risk": return "#ef4444";  // Red
      case "Severe Flood": return "#7f1d1d"; // Dark Red
      default: return "#3b82f6";
    }
  };

  if (!isAuthenticated) {
    return (
      <div style={{
        display: 'flex', justifyContent: 'center', alignItems: 'center',
        minHeight: '100vh', backgroundColor: '#0b0f19', padding: '1.5rem'
      }}>
        <div className="glass-panel glow-blue" style={{
          width: '100%', maxWidth: '420px', padding: '2.5rem', borderRadius: '16px'
        }}>
          <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
            <div style={{
              display: 'inline-flex', padding: '1rem', borderRadius: '50%',
              backgroundColor: 'rgba(59, 130, 246, 0.1)', marginBottom: '1rem'
            }}>
              <ShieldAlert size={40} color="#3b82f6" />
            </div>
            <h1 style={{ fontSize: '2rem', fontWeight: 800, letterSpacing: '-0.05em', color: '#f8fafc' }}>
              HYDROGNN-NET
            </h1>
            <p style={{ color: '#94a3b8', fontSize: '0.875rem', marginTop: '0.25rem' }}>
              Tamil Nadu Spatio-Temporal Flood Intelligence
            </p>
          </div>
          
          <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600, marginBottom: '0.5rem' }}>
                Control Room Email
              </label>
              <input 
                type="email" 
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                style={{
                  width: '100%', padding: '0.75rem 1rem', borderRadius: '8px',
                  backgroundColor: '#131c2e', border: '1px solid rgba(255,255,255,0.08)',
                  color: '#f8fafc', outline: 'none'
                }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600, marginBottom: '0.5rem' }}>
                Access Key
              </label>
              <input 
                type="password" 
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                style={{
                  width: '100%', padding: '0.75rem 1rem', borderRadius: '8px',
                  backgroundColor: '#131c2e', border: '1px solid rgba(255,255,255,0.08)',
                  color: '#f8fafc', outline: 'none'
                }}
              />
            </div>
            
            {loginError && (
              <p style={{ color: '#ef4444', fontSize: '0.875rem', textAlign: 'center' }}>
                {loginError}
              </p>
            )}
            
            <button 
              type="submit" 
              className="btn-interactive"
              style={{
                width: '100%', padding: '0.85rem', borderRadius: '8px',
                backgroundColor: '#3b82f6', border: 'none', color: '#f8fafc',
                fontWeight: 600, cursor: 'pointer', display: 'flex',
                alignItems: 'center', justifyContent: 'center', gap: '0.5rem',
                marginTop: '0.5rem'
              }}
            >
              <LogIn size={18} /> Authenticate Session
            </button>
          </form>
          <div style={{ textAlign: 'center', marginTop: '1.5rem', fontSize: '0.75rem', color: '#64748b' }}>
            Authorised personnel only
          </div>
        </div>
      </div>
    );
  }

  // Get active selected station details
  const selectedStation = dashboardData?.stations.find(s => s.id === selectedStationId);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', backgroundColor: '#0b0f19' }}>
      {/* Header bar */}
      <header className="glass-panel" style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '1rem 2rem', borderRadius: '0', borderLeft: 'none', borderRight: 'none', borderTop: 'none',
        zIndex: 1000
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{ backgroundColor: 'rgba(59, 130, 246, 0.1)', padding: '0.5rem', borderRadius: '8px' }}>
            <Activity size={24} color="#3b82f6" />
          </div>
          <div>
            <h1 style={{ fontSize: '1.25rem', fontWeight: 800, color: '#f8fafc', letterSpacing: '-0.02em', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              HYDROGNN-NET <span style={{ fontSize: '0.75rem', padding: '0.1rem 0.4rem', borderRadius: '4px', backgroundColor: 'rgba(6, 182, 212, 0.2)', color: '#06b6d4' }}>PROTOTYPE</span>
            </h1>
            <p style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Real-Time Multi-Scale Flood Routing Decision Support System</p>
          </div>
        </div>
        
        {/* Navigation tabs */}
        <div style={{ display: 'flex', gap: '0.5rem', backgroundColor: '#131c2e', padding: '0.25rem', borderRadius: '8px' }}>
          <button 
            onClick={() => setActiveTab("map")}
            style={{
              padding: '0.5rem 1rem', border: 'none', borderRadius: '6px', cursor: 'pointer',
              color: activeTab === "map" ? "#f8fafc" : "#94a3b8", fontWeight: 600, fontSize: '0.875rem',
              backgroundColor: activeTab === "map" ? "#1b2640" : "transparent"
            }}
          >
            <Compass size={16} style={{ marginRight: '0.35rem', verticalAlign: 'middle' }} /> Spatial Map
          </button>
          <button 
            onClick={() => setActiveTab("reservoirs")}
            style={{
              padding: '0.5rem 1rem', border: 'none', borderRadius: '6px', cursor: 'pointer',
              color: activeTab === "reservoirs" ? "#f8fafc" : "#94a3b8", fontWeight: 600, fontSize: '0.875rem',
              backgroundColor: activeTab === "reservoirs" ? "#1b2640" : "transparent"
            }}
          >
            <Database size={16} style={{ marginRight: '0.35rem', verticalAlign: 'middle' }} /> Reservoirs
          </button>
          <button 
            onClick={() => setActiveTab("alerts")}
            style={{
              padding: '0.5rem 1rem', border: 'none', borderRadius: '6px', cursor: 'pointer',
              color: activeTab === "alerts" ? "#f8fafc" : "#94a3b8", fontWeight: 600, fontSize: '0.875rem',
              backgroundColor: activeTab === "alerts" ? "#1b2640" : "transparent"
            }}
          >
            <AlertTriangle size={16} style={{ marginRight: '0.35rem', verticalAlign: 'middle' }} /> Warnings ({alerts.length})
          </button>
          <button 
            onClick={() => setActiveTab("chatbot")}
            style={{
              padding: '0.5rem 1rem', border: 'none', borderRadius: '6px', cursor: 'pointer',
              color: activeTab === "chatbot" ? "#f8fafc" : "#94a3b8", fontWeight: 600, fontSize: '0.875rem',
              backgroundColor: activeTab === "chatbot" ? "#1b2640" : "transparent"
            }}
          >
            <MessageSquare size={16} style={{ marginRight: '0.35rem', verticalAlign: 'middle' }} /> Assistant
          </button>
          <button
            onClick={() => setActiveTab("monitoring")}
            style={{
              padding: '0.5rem 1rem', border: 'none', borderRadius: '6px', cursor: 'pointer',
              color: activeTab === "monitoring" ? "#f8fafc" : "#94a3b8", fontWeight: 600, fontSize: '0.875rem',
              backgroundColor: activeTab === "monitoring" ? "#1b2640" : "transparent"
            }}
          >
            <Cpu size={16} style={{ marginRight: '0.35rem', verticalAlign: 'middle' }} /> Monitoring
          </button>
          <button
            onClick={() => setActiveTab("replay")}
            style={{
              padding: '0.5rem 1rem', border: 'none', borderRadius: '6px', cursor: 'pointer',
              color: activeTab === "replay" ? "#f8fafc" : "#94a3b8", fontWeight: 600, fontSize: '0.875rem',
              backgroundColor: activeTab === "replay" ? "#1b2640" : "transparent"
            }}
          >
            <Activity size={16} style={{ marginRight: '0.35rem', verticalAlign: 'middle' }} /> Replay
          </button>
        </div>
        
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          {/* Live refresh indicator */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.75rem', color: refreshing ? '#f59e0b' : '#10b981' }}>
              <span style={{
                width: '8px', height: '8px', borderRadius: '50%',
                backgroundColor: refreshing ? '#f59e0b' : '#10b981',
                display: 'inline-block',
                animation: refreshing ? 'pulse 1s infinite' : 'none'
              }}></span>
              {refreshing ? 'Refreshing…' : 'Live · 60s'}
            </div>
            {lastRefreshed && (
              <span style={{ fontSize: '0.65rem', color: '#475569' }}>
                Updated {lastRefreshed.toLocaleTimeString()}
              </span>
            )}
          </div>
          <button 
            onClick={handleLogout}
            style={{
              backgroundColor: 'rgba(239, 68, 68, 0.1)', border: 'none', cursor: 'pointer',
              padding: '0.5rem', borderRadius: '6px', color: '#ef4444', display: 'flex', alignItems: 'center'
            }}
            title="Log Out"
          >
            <LogOut size={16} />
          </button>
        </div>
      </header>

      {/* Issue #5: Backend error banner — shown when dashboard/alerts fail silently */}
      {backendError && (
        <div style={{
          backgroundColor: 'rgba(127, 29, 29, 0.85)', border: '1px solid #ef4444',
          borderRadius: '8px', padding: '0.75rem 1.25rem', margin: '0 1.5rem',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem',
          color: '#fca5a5', fontSize: '0.875rem'
        }}>
          <span><strong>⚠ Connection Error:</strong> {backendError}</span>
          <button
            onClick={() => { setBackendError(null); fetchDashboard(); fetchAlerts(); }}
            style={{
              backgroundColor: '#ef4444', border: 'none', borderRadius: '6px',
              padding: '0.35rem 0.85rem', color: '#fff', cursor: 'pointer', fontWeight: 600,
              fontSize: '0.8rem', whiteSpace: 'nowrap'
            }}
          >
            Retry Now
          </button>
        </div>
      )}

      {/* Main dashboard content grids */}
      {loadingDash ? (
        <div style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
          <div style={{ textAlign: 'center', color: '#94a3b8' }}>
            <Cpu size={40} className="pulse-warning" color="#3b82f6" />
            <p style={{ marginTop: '1rem' }}>Fetching Control Room telemetry...</p>
          </div>
        </div>
      ) : (
        <main style={{ flex: 1, padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem', overflow: 'hidden' }}>
          
          {/* Active alerts banner if critical ones exist */}
          {alerts.filter(a => a.severity === 'CRITICAL').length > 0 && (
            <div className="glass-panel glow-red" style={{
              display: 'flex', gap: '1rem', alignItems: 'center', padding: '1rem',
              borderColor: '#ef4444', backgroundColor: 'rgba(127, 29, 29, 0.2)', color: '#fca5a5',
              borderRadius: '8px'
            }}>
              <AlertTriangle size={24} color="#ef4444" className="pulse-warning" />
              <div style={{ flex: 1 }}>
                <strong>CRITICAL HYDROLOGICAL FLOOD WARNINGS IN EFFECT</strong>
                <p style={{ fontSize: '0.875rem', opacity: 0.9 }}>
                  Multiple stations have exceeded warning thresholds. Flow propagation downstream actively rising.
                </p>
              </div>
              <button 
                onClick={() => setActiveTab("alerts")}
                style={{
                  backgroundColor: '#ef4444', color: '#fff', border: 'none', borderRadius: '4px',
                  padding: '0.4rem 0.8rem', fontSize: '0.75rem', fontWeight: 600, cursor: 'pointer'
                }}
              >
                Inspect Alerts
              </button>
            </div>
          )}

          {/* MAIN VIEW PANELS */}
          {activeTab === "map" && (
            <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '320px 1fr 360px', gap: '1.5rem', minHeight: 0 }}>
              
              {/* Left Column: Stat summaries and station details selector */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', overflowY: 'auto' }}>
                {/* Stats cards Grid */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '1rem' }}>
                  <div className="glass-panel" style={{ padding: '1rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <div style={{ backgroundColor: 'rgba(239, 68, 68, 0.1)', padding: '0.5rem', borderRadius: '8px' }}>
                      <AlertTriangle size={20} color="#ef4444" />
                    </div>
                    <div>
                      <div style={{ fontSize: '1.5rem', fontWeight: 800 }}>{dashboardData?.active_warnings}</div>
                      <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Active Warnings</div>
                    </div>
                  </div>
                  <div className="glass-panel" style={{ padding: '1rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <div style={{ backgroundColor: 'rgba(6, 182, 212, 0.1)', padding: '0.5rem', borderRadius: '8px' }}>
                      <Database size={20} color="#06b6d4" />
                    </div>
                    <div>
                      <div style={{ fontSize: '1.5rem', fontWeight: 800 }}>{dashboardData?.average_reservoir_fill_pct}%</div>
                      <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Reservoir Avg Fill</div>
                    </div>
                  </div>
                  <div className="glass-panel" style={{ padding: '1rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <div style={{ backgroundColor: 'rgba(16, 185, 129, 0.1)', padding: '0.5rem', borderRadius: '8px' }}>
                      <Droplet size={20} color="#10b981" />
                    </div>
                    <div>
                      <div style={{ fontSize: '1.5rem', fontWeight: 800 }}>{dashboardData?.heavy_rain_stations_count}</div>
                      <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Storm Active Zones</div>
                    </div>
                  </div>
                </div>

                {/* Station details panel */}
                <div className="glass-panel" style={{ padding: '1.25rem', flex: 1, display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <h3 style={{ fontSize: '1rem', color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <MapPin size={18} color="#3b82f6" /> Basin Station Telemetry
                  </h3>
                  
                  {/* Select dropdown list */}
                  <select 
                    value={selectedStationId}
                    onChange={(e) => setSelectedStationId(e.target.value)}
                    style={{
                      width: '100%', padding: '0.75rem', borderRadius: '8px',
                      backgroundColor: '#131c2e', border: '1px solid rgba(255,255,255,0.08)',
                      color: '#f8fafc', outline: 'none', cursor: 'pointer'
                    }}
                  >
                    {dashboardData?.stations.map(st => (
                      <option key={st.id} value={st.id}>{st.name} ({st.basin})</option>
                    ))}
                  </select>

                  {selectedStation && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.875rem' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '0.4rem', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                        <span style={{ color: '#94a3b8' }}>Basin:</span>
                        <strong style={{ color: '#f8fafc' }}>{selectedStation.basin}</strong>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '0.4rem', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                        <span style={{ color: '#94a3b8' }}>Type:</span>
                        <strong style={{ color: '#f8fafc', textTransform: 'capitalize' }}>{selectedStation.type}</strong>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '0.4rem', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                        <span style={{ color: '#94a3b8' }}>Elevation (DEM):</span>
                        <strong style={{ color: '#f8fafc' }}>{selectedStation.elevation} m</strong>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '0.4rem', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                        <span style={{ color: '#94a3b8' }}>Current Level:</span>
                        <strong style={{ color: '#f8fafc' }}>{selectedStation.water_level} m</strong>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '0.4rem', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                        <span style={{ color: '#94a3b8' }}>Warning / Danger:</span>
                        <strong style={{ color: '#ef4444' }}>{selectedStation.danger_level} m</strong>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '0.4rem', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                        <span style={{ color: '#94a3b8' }}>Discharge Rate:</span>
                        <strong style={{ color: '#f8fafc' }}>{selectedStation.discharge} m³/s</strong>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '0.4rem', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                        <span style={{ color: '#94a3b8' }}>Soil Moisture:</span>
                        <strong style={{ color: '#f8fafc' }}>{Math.round(selectedStation.soil_moisture * 100)}%</strong>
                      </div>

                      {/* Priority 3 — Weather fields from backend (temperature, humidity, wind, rain) */}
                      {selectedStation.rain_observed != null && (
                        <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '0.4rem', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                          <span style={{ color: '#94a3b8' }}>Rain Observed:</span>
                          <strong style={{ color: '#06b6d4' }}>{selectedStation.rain_observed} mm</strong>
                        </div>
                      )}
                      {selectedStation.temperature != null && (
                        <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '0.4rem', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                          <span style={{ color: '#94a3b8' }}>Temperature:</span>
                          <strong style={{ color: '#f8fafc' }}>{selectedStation.temperature} °C</strong>
                        </div>
                      )}
                      {selectedStation.humidity != null && (
                        <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '0.4rem', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                          <span style={{ color: '#94a3b8' }}>Humidity:</span>
                          <strong style={{ color: '#f8fafc' }}>{selectedStation.humidity}%</strong>
                        </div>
                      )}
                      {selectedStation.wind_speed != null && (
                        <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '0.4rem', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                          <span style={{ color: '#94a3b8' }}>Wind Speed:</span>
                          <strong style={{ color: '#f8fafc' }}>{selectedStation.wind_speed} m/s</strong>
                        </div>
                      )}

                      {/* Severity Chip */}
                      <div style={{
                        marginTop: '0.5rem', padding: '0.75rem', borderRadius: '6px',
                        backgroundColor: getSeverityColor(selectedStation.risk_level) + '22',
                        border: `1px solid ${getSeverityColor(selectedStation.risk_level)}`,
                        textAlign: 'center', color: getSeverityColor(selectedStation.risk_level),
                        fontWeight: 700
                      }}>
                        {selectedStation.risk_level}
                      </div>

                      {/* River Level Source Badge */}
                      {(() => {
                        const src = selectedStation.data_source || 'unknown';
                        const isLive = ['nasa_power', 'open_meteo', 'openweather', 'copernicus'].some(s => src.toLowerCase().includes(s));
                        return (
                          <div style={{
                            display: 'flex', alignItems: 'center', gap: '0.35rem',
                            fontSize: '0.7rem', padding: '0.35rem 0.6rem', borderRadius: '4px',
                            backgroundColor: isLive ? 'rgba(16, 185, 129, 0.1)' : 'rgba(245, 158, 11, 0.1)',
                            border: `1px solid ${isLive ? 'rgba(16,185,129,0.4)' : 'rgba(245,158,11,0.4)'}`,
                            color: isLive ? '#10b981' : '#f59e0b',
                            alignSelf: 'flex-start'
                          }}>
                            <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: isLive ? '#10b981' : '#f59e0b', display: 'inline-block', flexShrink: 0 }}></span>
                            River: {isLive ? `Live · ${src}` : `Sim · ${src}`}
                          </div>
                        );
                      })()}
                      {/* Weather Source Badge — Priority 3 */}
                      {selectedStation.weather_source && (() => {
                        const wsrc = selectedStation.weather_source;
                        const isLiveWx = ['openweather', 'nasa_power', 'open_meteo'].some(s => wsrc.toLowerCase().includes(s));
                        return (
                          <div style={{
                            display: 'flex', alignItems: 'center', gap: '0.35rem',
                            fontSize: '0.7rem', padding: '0.35rem 0.6rem', borderRadius: '4px',
                            backgroundColor: isLiveWx ? 'rgba(6, 182, 212, 0.1)' : 'rgba(245, 158, 11, 0.1)',
                            border: `1px solid ${isLiveWx ? 'rgba(6,182,212,0.4)' : 'rgba(245,158,11,0.4)'}`,
                            color: isLiveWx ? '#06b6d4' : '#f59e0b',
                            alignSelf: 'flex-start'
                          }}>
                            <Wind size={10} style={{ flexShrink: 0 }} />
                            Weather: {isLiveWx ? `Live · ${wsrc}` : `Sim · ${wsrc}`}
                          </div>
                        );
                      })()}
                    </div>
                  )}
                </div>
              </div>

              {/* Middle Column: GIS Leaflet Map and Recharts Routing Wave */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', minHeight: 0 }}>
                {/* GIS Map */}
                <div style={{ flex: 1, position: 'relative' }}>
                  <MapContainer 
                    center={TN_CENTER} 
                    zoom={7.2} 
                    style={{ width: '100%', height: '100%' }}
                  >
                    <TileLayer
                      attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
                      url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
                    />
                    {dashboardData?.stations.map(st => (
                      <CircleMarker
                        key={st.id}
                        center={[st.lat, st.lon]}
                        pathOptions={{
                          color: getSeverityColor(st.risk_level),
                          fillColor: getSeverityColor(st.risk_level),
                          fillOpacity: 0.85,
                          weight: selectedStationId === st.id ? 3 : 1
                        }}
                        radius={st.type === 'reservoir' ? 10 : 6}
                        eventHandlers={{
                          click: () => setSelectedStationId(st.id)
                        }}
                      >
                        <Popup>
                          <div style={{ color: '#0b0f19', fontSize: '0.875rem' }}>
                            <strong style={{ fontSize: '1rem' }}>{st.name}</strong><br/>
                            Basin: {st.basin}<br/>
                            Water Level: {st.water_level}m / Danger: {st.danger_level}m<br/>
                            Risk State: <strong>{st.risk_level}</strong>
                          </div>
                        </Popup>
                      </CircleMarker>
                    ))}
                  </MapContainer>
                </div>


                {/* ── Station Comparison Panel (Phase 9) ─────────────────── */}
                <div className="glass-panel" style={{ padding: '0.75rem 1rem', display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                  <button
                    onClick={() => setShowComparePanel(v => !v)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 5,
                      padding: '4px 12px', borderRadius: 6,
                      border: `1px solid ${showComparePanel ? 'rgba(168,85,247,0.5)' : 'rgba(255,255,255,0.08)'}`,
                      background: showComparePanel ? 'rgba(168,85,247,0.1)' : 'transparent',
                      color: showComparePanel ? '#a855f7' : '#64748b', fontSize: '0.78rem', cursor: 'pointer'
                    }}
                  >
                    <GitCompare size={13} /> Compare Stations ({compareStations.length}/3)
                  </button>

                  {showComparePanel && dashboardData?.stations && (
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                      {dashboardData.stations
                        .filter(s => s.id !== selectedStationId)
                        .slice(0, 12)
                        .map(s => {
                          const isSelected = compareStations.includes(s.id);
                          return (
                            <button key={s.id}
                              onClick={() => {
                                if (isSelected) {
                                  setCompareStations(cs => cs.filter(id => id !== s.id));
                                  setCompareData(cd => cd.filter(c => c.stationId !== s.id));
                                } else if (compareStations.length < 3) {
                                  setCompareStations(cs => [...cs, s.id]);
                                }
                              }}
                              style={{
                                padding: '2px 9px', borderRadius: 4, fontSize: '0.7rem', cursor: 'pointer',
                                border: `1px solid ${isSelected ? 'rgba(168,85,247,0.5)' : 'rgba(255,255,255,0.07)'}`,
                                background: isSelected ? 'rgba(168,85,247,0.12)' : 'transparent',
                                color: isSelected ? '#c084fc' : '#64748b',
                              }}
                            >
                              {isSelected && '✓ '}{s.name || s.id}
                            </button>
                          );
                        })}
                    </div>
                  )}

                  {/* Active compare chips */}
                  {compareStations.map((sid, i) => (
                    <span key={sid} style={{
                      display: 'inline-flex', alignItems: 'center', gap: 4,
                      padding: '2px 8px', borderRadius: 4, fontSize: '0.7rem',
                      background: ['rgba(168,85,247,0.15)','rgba(245,158,11,0.15)','rgba(6,182,212,0.15)'][i] || 'rgba(255,255,255,0.08)',
                      color: ['#c084fc','#fbbf24','#06b6d4'][i] || '#94a3b8',
                      border: `1px solid ${['rgba(168,85,247,0.3)','rgba(245,158,11,0.3)','rgba(6,182,212,0.3)'][i] || 'rgba(255,255,255,0.1)'}`,
                    }}>
                      {sid}
                      <span style={{ cursor: 'pointer', opacity: 0.7 }}
                        onClick={() => { setCompareStations(cs => cs.filter(id => id !== sid)); setCompareData(cd => cd.filter(c => c.stationId !== sid)); }}>
                        <X size={10}/>
                      </span>
                    </span>
                  ))}

                  {/* Routing metadata */}
                  {predictionData?.routing_metadata && (
                    <span style={{ marginLeft: 'auto', fontSize: '0.68rem', color: '#334155' }}>
                      {predictionData.routing_metadata.observed_points || '?'} obs +{' '}
                      {predictionData.routing_metadata.forecast_points || '?'} fc · Nash-Sutcliffe IUH
                    </span>
                  )}
                </div>

                {/* ── Scientific Hydrograph (HydroChart) ─────────────────── */}
                <div className="glass-panel" style={{ height: '520px', padding: '1rem 1.25rem', display: 'flex', flexDirection: 'column' }}>
                  <HydroChart
                    predictionData={predictionData}
                    stationName={
                      dashboardData?.stations?.find(s => s.id === selectedStationId)?.name
                      || selectedStationId
                    }
                    loading={loadingPred}
                    compareData={compareData}
                  />
                </div>
              </div>

              {/* Right Column: Explainable AI and mini-Chatbot */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', overflowY: 'auto' }}>
                {/* Explainable AI */}
                <div className="glass-panel" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  <h3 style={{ fontSize: '1rem', color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Cpu size={18} color="#a855f7" /> Explainable AI (SHAP &amp; GAT)
                  </h3>

                  {predictionData ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.8125rem' }}>
                      <p style={{ color: '#94a3b8', lineHeight: 1.4 }}>
                        Feature attribution weights derived from input sensitivity analysis:
                      </p>

                      {/* SHAP attributions */}
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginTop: '0.25rem' }}>
                        {predictionData.xai_attributions && Object.keys(predictionData.xai_attributions).length > 0 ? (
                          Object.entries(predictionData.xai_attributions)
                            .sort(([, a], [, b]) => b - a)
                            .map(([key, val]) => (
                              <div key={key}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.2rem' }}>
                                  <span>{key}</span>
                                  <strong>{val}%</strong>
                                </div>
                                <div style={{ width: '100%', height: '6px', backgroundColor: '#1b2640', borderRadius: '3px' }}>
                                  <div style={{ width: `${Math.min(val, 100)}%`, height: '100%', backgroundColor: '#a855f7', borderRadius: '3px' }}></div>
                                </div>
                              </div>
                            ))
                        ) : (
                          <div style={{ color: '#64748b', fontSize: '0.8125rem', fontStyle: 'italic', padding: '0.5rem 0' }}>
                            No explanation available — model weights not yet loaded or feature sequence empty.
                          </div>
                        )}
                      </div>

                      {/* GAT Attention */}
                      <div style={{ marginTop: '0.75rem', padding: '0.75rem', borderRadius: '6px', backgroundColor: '#131c2e', border: '1px solid var(--glass-border)' }}>
                        <span style={{ fontWeight: 600, color: '#f8fafc', display: 'block', marginBottom: '0.4rem' }}>Graph Attention Confluence:</span>
                        {predictionData.gat_attention && predictionData.gat_attention.length > 0 ? (
                          <div style={{ color: '#94a3b8', display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                            {predictionData.gat_attention.map((edge, i) => (
                              <div key={i}>
                                ● {edge.weight_pct}% attention from <strong>{edge.source}</strong>
                                <span style={{ color: '#475569', fontSize: '0.75rem' }}> ({edge.description})</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div style={{ color: '#64748b', fontStyle: 'italic', fontSize: '0.8125rem' }}>
                            No attention data available — model checkpoint not loaded.
                          </div>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div style={{ color: '#64748b', fontSize: '0.875rem', textAlign: 'center', padding: '1rem' }}>
                      Awaiting model evaluation context.
                    </div>
                  )}
                </div>

                {/* Sentinel-2 Satellite Intelligence Panel */}
                <div className="glass-panel" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                  <h3 style={{ fontSize: '0.9375rem', color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                    <Database size={16} color="#06b6d4" /> Sentinel-2 Satellite
                  </h3>

                  {!satelliteData ? (
                    <div style={{ color: '#64748b', fontSize: '0.8125rem', fontStyle: 'italic' }}>
                      Loading satellite data…
                    </div>
                  ) : satelliteData.status === 'ingesting' ? (
                    <div style={{ fontSize: '0.8125rem' }}>
                      <span className="pulse-warning" style={{ color: '#f59e0b' }}>
                        ⟳ {satelliteData.message}
                      </span>
                    </div>
                  ) : satelliteData.scenes && satelliteData.scenes.length > 0 ? (() => {
                    // Find scene for currently selected station, else show most recent
                    const stScene = satelliteData.scenes.find(sc => sc.station_id === selectedStationId)
                                 || satelliteData.scenes[0];
                    return (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', fontSize: '0.8125rem' }}>
                        <div style={{
                          padding: '0.6rem', borderRadius: '6px',
                          backgroundColor: 'rgba(6, 182, 212, 0.08)',
                          border: '1px solid rgba(6,182,212,0.25)'
                        }}>
                          <div style={{ color: '#06b6d4', fontWeight: 600, marginBottom: '0.3rem' }}>
                            {stScene.station_name}
                          </div>
                          <div style={{ color: '#94a3b8', display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                            <span>📅 Capture: <strong style={{ color: '#f8fafc' }}>{stScene.capture_date}</strong></span>
                            <span>🛰 Age: <strong style={{ color: stScene.age_days <= 5 ? '#10b981' : stScene.age_days <= 14 ? '#f59e0b' : '#ef4444' }}>{stScene.age_days}d old</strong></span>
                            <span>📡 Source: <strong style={{ color: '#f8fafc' }}>{stScene.source}</strong></span>
                            <span style={{ fontSize: '0.72rem', color: '#475569', fontFamily: 'monospace', wordBreak: 'break-all' }}>{stScene.id}</span>
                          </div>
                        </div>
                        <div style={{ color: '#475569', fontSize: '0.75rem' }}>
                          {satelliteData.total_scenes} scenes · Last: {satelliteData.last_ingested}
                        </div>
                      </div>
                    );
                  })() : (
                    <div style={{ color: '#64748b', fontSize: '0.8125rem', fontStyle: 'italic' }}>
                      No satellite scenes ingested yet. Backend will retry on next scheduler tick.
                    </div>
                  )}
                </div>

                {/* Floating mini chatbot */}
                <div className="glass-panel" style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: '280px' }}>
                  <div style={{ padding: '0.75rem 1rem', borderBottom: '1px solid var(--glass-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <strong style={{ fontSize: '0.875rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                      <MessageSquare size={16} color="#06b6d4" /> Control Room Assistant
                    </strong>
                    <span style={{ fontSize: '0.75rem', color: '#64748b' }}>Rule-based · Live Context</span>
                  </div>
                  
                  {/* Message stack */}
                  <div style={{ flex: 1, padding: '1rem', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.8125rem' }}>
                    {chatHistory.slice(-4).map((msg, i) => (
                      <div key={i} style={{
                        alignSelf: msg.sender === "user" ? "flex-end" : "flex-start",
                        backgroundColor: msg.sender === "user" ? "#3b82f6" : "#131c2e",
                        color: '#f8fafc', padding: '0.5rem 0.75rem', borderRadius: '8px',
                        maxWidth: '85%', border: msg.sender === "bot" ? '1px solid var(--glass-border)' : 'none'
                      }}>
                        {msg.text}
                      </div>
                    ))}
                    {sendingChat && <div style={{ color: '#64748b' }}>Analyzing hydrology vectors...</div>}
                    <div ref={chatEndRef} />
                  </div>
                  
                  {/* Message Input form */}
                  <form onSubmit={handleSendChat} style={{ padding: '0.75rem', borderTop: '1px solid var(--glass-border)', display: 'flex', gap: '0.5rem' }}>
                    <input 
                      type="text" 
                      placeholder="Ask about Cauvery levels, releases..." 
                      value={chatMessage}
                      onChange={(e) => setChatMessage(e.target.value)}
                      style={{
                        flex: 1, padding: '0.5rem 0.75rem', borderRadius: '6px',
                        backgroundColor: '#131c2e', border: '1px solid rgba(255,255,255,0.08)',
                        color: '#f8fafc', fontSize: '0.8125rem', outline: 'none'
                      }}
                    />
                    <button 
                      type="submit" 
                      style={{
                        padding: '0.5rem', borderRadius: '6px', backgroundColor: '#3b82f6',
                        border: 'none', color: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center'
                      }}
                    >
                      <Send size={14} />
                    </button>
                  </form>
                </div>
              </div>
            </div>
          )}

          {/* RESERVOIRS VIEW PANEL */}
          {activeTab === "reservoirs" && (
            <div style={{ flex: 1, overflowY: 'auto' }}>
              <h2 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Database color="#06b6d4" /> Reservoir Storage Capacity &amp; Spillway Release
              </h2>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '1.5rem' }}>
                {dashboardData?.reservoirs.map(res => {
                  const stationInfo = dashboardData.stations.find(s => s.id === res.id);

                  // Color based on storage level (5-tier)
                  const strokeColor =
                    res.storage_pct > 90 ? "#ef4444" :
                    res.storage_pct > 80 ? "#f97316" :
                    res.storage_pct > 65 ? "#f59e0b" :
                    res.storage_pct > 30 ? "#06b6d4" :
                                           "#8b5cf6";

                  // Status badge color from backend-provided status field
                  const statusBgColor =
                    res.status === "CRITICAL INFLOW" ? 'rgba(239,68,68,0.15)' :
                    res.status === "HIGH ALERT"       ? 'rgba(249,115,22,0.15)' :
                    res.status === "ELEVATED"         ? 'rgba(245,158,11,0.15)' :
                    res.status === "LOW LEVEL"        ? 'rgba(139,92,246,0.15)' :
                                                        'rgba(6,182,212,0.1)';

                  return (
                    <div key={res.id} className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                        <div>
                          <h3 style={{ fontSize: '1.15rem', color: '#f8fafc' }}>{res.name}</h3>
                          <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Basin: {stationInfo?.basin}</span>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.3rem' }}>
                          {/* Status from backend */}
                          <span style={{
                            fontSize: '0.75rem', fontWeight: 700, padding: '0.2rem 0.5rem', borderRadius: '4px',
                            backgroundColor: statusBgColor,
                            color: strokeColor
                          }}>
                            {res.status || (res.storage_pct > 90 ? "CRITICAL INFLOW" : "NORMAL")}
                          </span>
                          {/* Data source badge */}
                          <span style={{ fontSize: '0.65rem', color: '#475569', padding: '0.1rem 0.4rem', borderRadius: '3px', backgroundColor: 'rgba(255,255,255,0.04)' }}>
                            src: {res.data_source || 'computed'}
                          </span>
                        </div>
                      </div>

                      {/* Progress Bar */}
                      <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.875rem', marginBottom: '0.4rem' }}>
                          <span style={{ color: '#94a3b8' }}>Storage Capacity Filled:</span>
                          <strong style={{ color: '#f8fafc' }}>{res.storage_pct}%</strong>
                        </div>
                        <div style={{ width: '100%', height: '10px', backgroundColor: '#131c2e', borderRadius: '5px', overflow: 'hidden', border: '1px solid rgba(255,255,255,0.04)' }}>
                          <div style={{
                            width: `${res.storage_pct}%`, height: '100%',
                            backgroundColor: strokeColor, borderRadius: '5px',
                            transition: 'width 1s ease-in-out'
                          }}></div>
                        </div>
                      </div>

                      {/* Info Grid */}
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', fontSize: '0.875rem', marginTop: '0.5rem' }}>
                        <div style={{ padding: '0.75rem', borderRadius: '6px', backgroundColor: '#131c2e' }}>
                          <span style={{ color: '#94a3b8', fontSize: '0.75rem', display: 'block' }}>Current Volume</span>
                          <strong style={{ color: '#f8fafc', fontSize: '1.1rem' }}>{res.current_storage_mcft} Mcft</strong>
                          <span style={{ fontSize: '0.75rem', color: '#64748b' }}>Max: {res.capacity_mcft} Mcft</span>
                        </div>
                        <div style={{ padding: '0.75rem', borderRadius: '6px', backgroundColor: '#131c2e' }}>
                          <span style={{ color: '#94a3b8', fontSize: '0.75rem', display: 'block' }}>Spillway Release</span>
                          <strong style={{ color: '#ef4444', fontSize: '1.1rem' }}>{res.release_cumecs} m³/s</strong>
                          <span style={{ fontSize: '0.75rem', color: '#64748b' }}>Controlled gate discharge</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* ALERTS / WARNINGS VIEW PANEL */}
          {activeTab === "alerts" && (
            <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <h2 style={{ fontSize: '1.5rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <AlertTriangle color="#ef4444" /> Active Hydro-Meteorological Warnings & Advisories ({alerts.length})
              </h2>
              <p style={{ color: '#94a3b8', fontSize: '0.875rem' }}>
                De-duplicated decision warnings triggered by spatio-temporal water levels exceeding threshold danger bands.
              </p>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '0.5rem' }}>
                {alerts.length > 0 ? (
                  alerts.map((al) => (
                    <div key={al.id} className="glass-panel" style={{
                      padding: '1.25rem', borderLeft: `4px solid ${al.severity === 'CRITICAL' ? '#ef4444' : '#f59e0b'}`,
                      display: 'flex', gap: '1.25rem', alignItems: 'start'
                    }}>
                      <div style={{
                        padding: '0.5rem', borderRadius: '8px', 
                        backgroundColor: al.severity === 'CRITICAL' ? 'rgba(239,68,68,0.1)' : 'rgba(245,158,11,0.1)'
                      }}>
                        <ShieldAlert size={20} color={al.severity === 'CRITICAL' ? '#ef4444' : '#f59e0b'} />
                      </div>
                      
                      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <h3 style={{ fontSize: '1.1rem', color: '#f8fafc' }}>
                            {al.type.replace('_', ' ')}: {al.station_name}
                          </h3>
                          <span style={{ fontSize: '0.75rem', color: '#64748b' }}>{al.timestamp}</span>
                        </div>
                        <p style={{ fontSize: '0.875rem', color: '#cbd5e1', lineHeight: 1.4 }}>
                          {al.message}
                        </p>
                        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem' }}>
                          <span style={{ fontSize: '0.75rem', padding: '0.1rem 0.4rem', borderRadius: '4px', backgroundColor: '#131c2e', color: '#94a3b8' }}>
                            Basin: {al.basin}
                          </span>
                          <span style={{ 
                            fontSize: '0.75rem', padding: '0.1rem 0.4rem', borderRadius: '4px', 
                            backgroundColor: al.severity === 'CRITICAL' ? 'rgba(239,68,68,0.15)' : 'rgba(245,158,11,0.15)',
                            color: al.severity === 'CRITICAL' ? '#ef4444' : '#f59e0b',
                            fontWeight: 600
                          }}>
                            {al.severity} Severity
                          </span>
                        </div>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="glass-panel" style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>
                    <ShieldAlert size={32} style={{ marginBottom: '0.5rem' }} />
                    <p>No active flood warning metrics or spill release alarms recorded in the telemetry window.</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* CHATBOT FULL SCREEN VIEW PANEL */}
          {activeTab === "chatbot" && (
            <div className="glass-panel" style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
              <div style={{ padding: '1.25rem', borderBottom: '1px solid var(--glass-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <h3 style={{ fontSize: '1.1rem', color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <MessageSquare size={20} color="#3b82f6" /> Hydrological Intelligence Assistant
                  </h3>
                  <p style={{ fontSize: '0.75rem', color: '#94a3b8', marginTop: '0.15rem' }}>
                    Context grounded directly in basin telemetry warnings and reservoir capacities.
                  </p>
                </div>
                <button 
                  onClick={() => setChatHistory([{ sender: "bot", text: "History cleared. How can I help you analyze the basins today?" }])}
                  style={{
                    backgroundColor: '#1b2640', color: '#94a3b8', border: 'none', borderRadius: '6px',
                    padding: '0.4rem 0.8rem', fontSize: '0.75rem', cursor: 'pointer'
                  }}
                >
                  Clear History
                </button>
              </div>
              
              {/* Message Stack */}
              <div style={{ flex: 1, padding: '1.5rem', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {chatHistory.map((msg, i) => (
                  <div key={i} style={{
                    alignSelf: msg.sender === "user" ? "flex-end" : "flex-start",
                    backgroundColor: msg.sender === "user" ? "#3b82f6" : "#131c2e",
                    color: '#f8fafc', padding: '0.85rem 1.25rem', borderRadius: '12px',
                    maxWidth: '75%', border: msg.sender === "bot" ? '1px solid var(--glass-border)' : 'none',
                    lineHeight: 1.5, fontSize: '0.875rem',
                    boxShadow: '0 2px 8px rgba(0,0,0,0.2)'
                  }}>
                    {msg.text}
                  </div>
                ))}
                {sendingChat && (
                  <div style={{ alignSelf: 'flex-start', color: '#64748b', fontSize: '0.875rem' }}>
                    Assistant is thinking and compiling vector tokens...
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>
              
              {/* Suggested Questions Area */}
              <div style={{ padding: '0.75rem 1.5rem', borderTop: '1px solid var(--glass-border)', display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '0.75rem', color: '#64748b', alignSelf: 'center' }}>Suggested:</span>
                {[
                  "Are there any active warning alerts?",
                  "Show reservoir release status",
                  "Explain Cauvery Basin topology"
                ].map((txt, idx) => (
                  <button
                    key={idx}
                    onClick={() => { setChatMessage(txt); }}
                    style={{
                      backgroundColor: '#1b2640', color: '#3b82f6', border: '1px solid rgba(59, 130, 246, 0.2)',
                      borderRadius: '16px', padding: '0.35rem 0.8rem', fontSize: '0.75rem', cursor: 'pointer',
                      fontWeight: 500, transition: 'all 0.2s'
                    }}
                    className="btn-interactive"
                  >
                    {txt}
                  </button>
                ))}
              </div>

              {/* Chat Input form */}
              <form onSubmit={handleSendChat} style={{ padding: '1rem 1.5rem', borderTop: '1px solid var(--glass-border)', display: 'flex', gap: '0.75rem' }}>
                <input 
                  type="text" 
                  placeholder="Ask a question about the Tamil Nadu river network telemetry..." 
                  value={chatMessage}
                  onChange={(e) => setChatMessage(e.target.value)}
                  style={{
                    flex: 1, padding: '0.85rem 1.25rem', borderRadius: '8px',
                    backgroundColor: '#131c2e', border: '1px solid rgba(255,255,255,0.08)',
                    color: '#f8fafc', fontSize: '0.875rem', outline: 'none'
                  }}
                />
                <button 
                  type="submit" 
                  className="btn-interactive"
                  style={{
                    padding: '0.85rem 1.5rem', borderRadius: '8px', backgroundColor: '#3b82f6',
                    border: 'none', color: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center',
                    gap: '0.5rem', fontWeight: 600
                  }}
                >
                  Send Query <ChevronRight size={16} />
                </button>
              </form>
            </div>
          )}

          {/* PRIORITY 1 — MONITORING TAB */}
          {activeTab === "monitoring" && (
            <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h2 style={{ fontSize: '1.5rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Cpu color="#a855f7" /> System Monitoring &amp; Diagnostics
                </h2>
                <button
                  onClick={fetchMonitoring}
                  style={{ backgroundColor: '#1b2640', border: '1px solid rgba(168,85,247,0.3)', color: '#a855f7', borderRadius: '6px', padding: '0.4rem 1rem', fontSize: '0.8rem', cursor: 'pointer', fontWeight: 600 }}
                >
                  Refresh Now
                </button>
              </div>

              {!monitoringData ? (
                <div style={{ color: '#64748b', textAlign: 'center', padding: '2rem' }}>Loading monitoring diagnostics...</div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1.25rem' }}>

                  {/* Overall Status */}
                  <div className="glass-panel" style={{ padding: '1.25rem', borderLeft: `4px solid ${monitoringData.status === 'Healthy' ? '#10b981' : '#f59e0b'}` }}>
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600, marginBottom: '0.5rem' }}>System Status</div>
                    <div style={{ fontSize: '1.5rem', fontWeight: 800, color: monitoringData.status === 'Healthy' ? '#10b981' : '#f59e0b' }}>
                      {monitoringData.status}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: '#475569', marginTop: '0.25rem' }}>Last updated: {monitoringData.last_updated || 'N/A'}</div>
                  </div>

                  {/* Database Health */}
                  <div className="glass-panel" style={{ padding: '1.25rem' }}>
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600, marginBottom: '0.5rem' }}>Database Health</div>
                    <div style={{ fontWeight: 700, color: monitoringData.database_health === 'Healthy' ? '#10b981' : '#ef4444' }}>{monitoringData.database_health}</div>
                  </div>

                  {/* Scheduler Status */}
                  <div className="glass-panel" style={{ padding: '1.25rem' }}>
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600, marginBottom: '0.5rem' }}>Scheduler Status</div>
                    <div style={{ fontWeight: 700, color: monitoringData.scheduler_status === 'Healthy' ? '#10b981' : '#f59e0b', fontSize: '0.875rem' }}>{monitoringData.scheduler_status}</div>
                  </div>

                  {/* CPU & Memory */}
                  <div className="glass-panel" style={{ padding: '1.25rem' }}>
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600, marginBottom: '0.75rem' }}>System Resources</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                      <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8125rem', marginBottom: '0.2rem' }}>
                          <span style={{ color: '#94a3b8' }}>CPU Usage</span>
                          <strong style={{ color: '#f8fafc' }}>{monitoringData.system_metrics?.cpu_usage_pct ?? 0}%</strong>
                        </div>
                        <div style={{ width: '100%', height: '6px', backgroundColor: '#1b2640', borderRadius: '3px' }}>
                          <div style={{ width: `${Math.min(monitoringData.system_metrics?.cpu_usage_pct ?? 0, 100)}%`, height: '100%', backgroundColor: '#3b82f6', borderRadius: '3px', transition: 'width 0.5s ease' }}></div>
                        </div>
                      </div>
                      <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8125rem', marginBottom: '0.2rem' }}>
                          <span style={{ color: '#94a3b8' }}>Memory Usage</span>
                          <strong style={{ color: '#f8fafc' }}>{monitoringData.system_metrics?.memory_usage_pct ?? 0}%</strong>
                        </div>
                        <div style={{ width: '100%', height: '6px', backgroundColor: '#1b2640', borderRadius: '3px' }}>
                          <div style={{ width: `${Math.min(monitoringData.system_metrics?.memory_usage_pct ?? 0, 100)}%`, height: '100%', backgroundColor: monitoringData.system_metrics?.memory_usage_pct > 85 ? '#ef4444' : '#10b981', borderRadius: '3px', transition: 'width 0.5s ease' }}></div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Inference Latency */}
                  <div className="glass-panel" style={{ padding: '1.25rem' }}>
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600, marginBottom: '0.5rem' }}>Inference Latency</div>
                    <div style={{ fontSize: '1.5rem', fontWeight: 800, color: monitoringData.inference_latency_avg_ms > 0 ? '#06b6d4' : '#475569' }}>
                      {monitoringData.inference_latency_avg_ms > 0 ? `${monitoringData.inference_latency_avg_ms} ms` : 'No run yet'}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: '#475569', marginTop: '0.25rem' }}>Measured on last /predict call</div>
                  </div>

                  {/* API Latency */}
                  <div className="glass-panel" style={{ padding: '1.25rem' }}>
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600, marginBottom: '0.5rem' }}>API Latency (this call)</div>
                    <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#a855f7' }}>{monitoringData.api_latency_ms} ms</div>
                  </div>

                  {/* Data Drift */}
                  <div className="glass-panel" style={{ padding: '1.25rem' }}>
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600, marginBottom: '0.5rem' }}>Data Drift</div>
                    <div style={{ fontWeight: 700, color: monitoringData.data_drift === 'Stable' ? '#10b981' : '#f59e0b', fontSize: '0.875rem' }}>{monitoringData.data_drift}</div>
                  </div>

                  {/* Model Drift */}
                  <div className="glass-panel" style={{ padding: '1.25rem' }}>
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600, marginBottom: '0.5rem' }}>Model Registry</div>
                    <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: '0.8125rem', lineHeight: 1.4 }}>{monitoringData.model_drift}</div>
                  </div>

                  {/* Prediction Count */}
                  <div className="glass-panel" style={{ padding: '1.25rem' }}>
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600, marginBottom: '0.5rem' }}>Total Predictions (DB)</div>
                    <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#f8fafc' }}>{monitoringData.prediction_count?.toLocaleString() ?? 'N/A'}</div>
                  </div>

                </div>
              )}
            </div>
          )}

          {/* PRIORITY 2 — REPLAY TAB */}
          {activeTab === "replay" && (
            <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              <h2 style={{ fontSize: '1.5rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Activity color="#06b6d4" /> Historical Flood Replay Simulator
              </h2>
              <p style={{ color: '#94a3b8', fontSize: '0.875rem', marginTop: '-1rem' }}>
                Select a historical flood scenario and a station to replay the GNN prediction vs observed timeline.
              </p>

              {/* Controls row */}
              <div className="glass-panel" style={{ padding: '1.25rem', display: 'flex', gap: '1.5rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
                <div style={{ flex: 1, minWidth: '200px' }}>
                  <label style={{ display: 'block', fontSize: '0.75rem', color: '#94a3b8', fontWeight: 600, marginBottom: '0.4rem', textTransform: 'uppercase' }}>
                    Flood Scenario
                  </label>
                  <select
                    value={activeReplayEvent || ''}
                    onChange={e => setActiveReplayEvent(e.target.value)}
                    style={{ width: '100%', padding: '0.65rem', backgroundColor: '#131c2e', border: '1px solid rgba(255,255,255,0.08)', color: '#f8fafc', borderRadius: '6px', outline: 'none' }}
                  >
                    {replayEvents.map(ev => (
                      <option key={ev.name} value={ev.name}>{ev.name} ({ev.duration_days}d)</option>
                    ))}
                  </select>
                </div>
                <div style={{ flex: 1, minWidth: '200px' }}>
                  <label style={{ display: 'block', fontSize: '0.75rem', color: '#94a3b8', fontWeight: 600, marginBottom: '0.4rem', textTransform: 'uppercase' }}>
                    Station
                  </label>
                  <select
                    value={selectedStationId}
                    onChange={e => setSelectedStationId(e.target.value)}
                    style={{ width: '100%', padding: '0.65rem', backgroundColor: '#131c2e', border: '1px solid rgba(255,255,255,0.08)', color: '#f8fafc', borderRadius: '6px', outline: 'none' }}
                  >
                    {dashboardData?.stations.map(st => (
                      <option key={st.id} value={st.id}>{st.name}</option>
                    ))}
                  </select>
                </div>
                <button
                  onClick={() => fetchReplay(activeReplayEvent, selectedStationId)}
                  disabled={replayLoading || !activeReplayEvent}
                  style={{
                    padding: '0.65rem 1.5rem', backgroundColor: replayLoading ? '#1b2640' : '#06b6d4',
                    border: 'none', borderRadius: '6px', color: replayLoading ? '#64748b' : '#0b0f19',
                    fontWeight: 700, cursor: replayLoading ? 'not-allowed' : 'pointer', fontSize: '0.875rem',
                    display: 'flex', alignItems: 'center', gap: '0.5rem'
                  }}
                >
                  <Activity size={16} /> {replayLoading ? 'Simulating…' : 'Run Replay'}
                </button>
              </div>

              {/* Scenario info cards */}
              {replayEvents.length > 0 && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '1rem' }}>
                  {replayEvents.map(ev => (
                    <div
                      key={ev.name}
                      className="glass-panel"
                      onClick={() => setActiveReplayEvent(ev.name)}
                      style={{
                        padding: '1rem', cursor: 'pointer',
                        borderColor: activeReplayEvent === ev.name ? '#06b6d4' : 'var(--glass-border)',
                        backgroundColor: activeReplayEvent === ev.name ? 'rgba(6,182,212,0.05)' : 'transparent'
                      }}
                    >
                      <h4 style={{ color: '#f8fafc', fontSize: '0.9375rem', marginBottom: '0.4rem' }}>{ev.name}</h4>
                      <p style={{ fontSize: '0.8125rem', color: '#94a3b8', lineHeight: 1.4, marginBottom: '0.5rem' }}>{ev.description}</p>
                      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                        <span style={{ fontSize: '0.7rem', padding: '0.15rem 0.5rem', borderRadius: '4px', backgroundColor: '#131c2e', color: '#94a3b8' }}>
                          Duration: {ev.duration_days}d
                        </span>
                        {ev.critical_stations?.map(st => (
                          <span key={st} style={{ fontSize: '0.7rem', padding: '0.15rem 0.5rem', borderRadius: '4px', backgroundColor: 'rgba(239,68,68,0.1)', color: '#ef4444' }}>
                            {st}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Replay results */}
              {replayResult && (
                <div className="glass-panel" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <h3 style={{ color: '#f8fafc', fontSize: '1rem' }}>
                      Replay: {replayResult.event_name} — {replayResult.station_id}
                    </h3>
                    <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                      {replayResult.simulation_steps_count} simulation steps
                    </span>
                  </div>

                  {/* Timeline table */}
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
                      <thead>
                        <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                          {['Hour', 'Observed (m)', 'GNN Predicted (m)', 'Upper CI', 'Lower CI'].map(h => (
                            <th key={h} style={{ padding: '0.5rem 0.75rem', color: '#94a3b8', textAlign: 'left', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase' }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {replayResult.comparison_timeline?.map((row, i) => {
                          const diff = Math.abs(row.observed_actual - row.predicted_gnn);
                          return (
                            <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)', backgroundColor: i % 2 === 0 ? 'rgba(255,255,255,0.01)' : 'transparent' }}>
                              <td style={{ padding: '0.5rem 0.75rem', color: '#64748b' }}>{row.timestamp}</td>
                              <td style={{ padding: '0.5rem 0.75rem', color: '#10b981', fontWeight: 600 }}>{row.observed_actual}</td>
                              <td style={{ padding: '0.5rem 0.75rem', color: '#3b82f6', fontWeight: 600 }}>{row.predicted_gnn}</td>
                              <td style={{ padding: '0.5rem 0.75rem', color: '#475569' }}>{row.upper_bound}</td>
                              <td style={{ padding: '0.5rem 0.75rem', color: '#475569' }}>{row.lower_bound}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

        </main>
      )}

      {/* Footer bar */}
      <footer style={{
        textAlign: 'center', padding: '0.75rem', borderTop: '1px solid var(--glass-border)',
        fontSize: '0.75rem', color: '#64748b', backgroundColor: 'rgba(11, 15, 25, 0.9)'
      }}>
        HydroGNN-Net Decision Support Framework | Developed for Tamil Nadu State Disaster Management Command Center | 2026
      </footer>
    </div>
  );
}
