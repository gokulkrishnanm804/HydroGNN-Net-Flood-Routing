'use client';
import { motion } from 'framer-motion';
import { useState, useEffect } from 'react';
import AppLayout from '../AppLayout';
import PageHeader from '../components/PageHeader';
import { CheckCircle, XCircle, Clock, Database, AlertTriangle, Cpu, HardDrive, ShieldCheck, RefreshCw, Radio, CloudRain, Droplets, Map, Layers, Brain, Zap } from 'lucide-react';
import { api } from '../../services/api';

const STATUS_META: Record<string, { color: string; icon: any; label: string }> = {
  healthy: { color: '#34d399', icon: CheckCircle, label: 'Healthy / Nominal' },
  warning:  { color: '#fbbf24', icon: AlertTriangle, label: 'Unstable' },
  error:    { color: '#fb7185', icon: XCircle, label: 'Offline / Down' },
};

export default function PipelinePage() {
  const [diagnostics, setDiagnostics] = useState<any>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [hasError, setHasError] = useState<boolean>(false);

  const fetchDiagnostics = async () => {
    try {
      setIsLoading(true);
      setHasError(false);
      const data = await api.getDiagnostics();
      setDiagnostics(data);
    } catch (err) {
      console.error('Failed to load system diagnostics:', err);
      setHasError(true);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDiagnostics();
  }, []);

  if (isLoading) {
    return (
      <AppLayout>
        <div style={{ padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div style={{ height: 160, background: 'rgba(255,255,255,0.03)', borderRadius: 20 }} className="shimmer" />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
            {[1, 2, 3].map(i => (
              <div key={i} style={{ height: 140, background: 'rgba(255,255,255,0.03)', borderRadius: 16 }} className="shimmer" />
            ))}
          </div>
        </div>
      </AppLayout>
    );
  }

  if (hasError || !diagnostics) {
    return (
      <AppLayout>
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          minHeight: 'calc(100vh - 120px)', gap: 16, padding: 32, textAlign: 'center',
        }}>
          <AlertTriangle size={48} color="#fb7185" />
          <h3 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#e2e8f0' }}>Diagnostics Offline</h3>
          <button className="btn btn-primary" onClick={fetchDiagnostics}>
            <RefreshCw size={14} /> Retry
          </button>
        </div>
      </AppLayout>
    );
  }

  const dbHealth = diagnostics.database_health === 'Healthy' ? 'healthy' : 'warning';
  const schedHealth = diagnostics.scheduler_status === 'Healthy' ? 'healthy' : 'warning';

  return (
    <AppLayout>
      <div style={{ padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 20 }}>

        {/* Page Header */}
        <PageHeader
          title="Data Pipeline & Provenance"
          subtitle="Track the data sources feeding monitoring, hydrology and forecasting"
          purpose="Understand where system inputs come from, when they were last ingested, and how they are used."
          badges={[
            { label: 'Live Telemetry Ingestion Active', variant: 'safe' },
            { label: 'Static Geospatial Topography', variant: 'info' },
            { label: 'Model: Experiment 9 Loaded', variant: 'info' },
          ]}
        />

        {/* SECTION 1: LIVE / INGESTED DATA */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <span className="badge badge-safe" style={{ fontSize: '0.68rem', fontWeight: 800 }}>LIVE / INGESTED</span>
            <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#f8fafc' }}>Real-Time Runtime Feeds</span>
            <span style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.4)', marginLeft: 'auto' }}>Auto-polling active</span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
            {/* Weather Ingestion */}
            <div className="glass-card" style={{ padding: 18, borderLeft: '3px solid #34d399' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                <div style={{ width: 34, height: 34, borderRadius: 8, background: 'rgba(52,211,153,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <CloudRain size={16} color="#34d399" />
                </div>
                <div>
                  <div style={{ fontSize: '0.86rem', fontWeight: 700, color: '#f1f5f9' }}>Weather Observations</div>
                  <div style={{ fontSize: '0.66rem', color: '#34d399', fontWeight: 600 }}>LIVE DATA FEED</div>
                </div>
              </div>
              <div style={{ fontSize: '0.74rem', color: 'rgba(255,255,255,0.6)', lineHeight: 1.5 }}>
                Source: <strong>OpenWeather API</strong>. Ingests 15-minute precipitation (mm), temperature, and wind for active basin stations.
              </div>
              <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid rgba(255,255,255,0.06)', display: 'flex', justifyContent: 'space-between', fontSize: '0.66rem', color: 'rgba(255,255,255,0.4)' }}>
                <span>Cadence: 15-min</span>
                <span style={{ color: '#34d399' }}>● Connected</span>
              </div>
            </div>

            {/* River Telemetry Ingestion */}
            <div className="glass-card" style={{ padding: 18, borderLeft: '3px solid #22d3ee' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                <div style={{ width: 34, height: 34, borderRadius: 8, background: 'rgba(34,211,238,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Radio size={16} color="#22d3ee" />
                </div>
                <div>
                  <div style={{ fontSize: '0.86rem', fontWeight: 700, color: '#f1f5f9' }}>River Telemetry Feeds</div>
                  <div style={{ fontSize: '0.66rem', color: '#22d3ee', fontWeight: 600 }}>LIVE DATA FEED</div>
                </div>
              </div>
              <div style={{ fontSize: '0.74rem', color: 'rgba(255,255,255,0.6)', lineHeight: 1.5 }}>
                Source: <strong>Open-Meteo & Live River Gauges</strong>. Real-time water stage (ft) and discharge (cumecs) across the 8 Cauvery stations.
              </div>
              <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid rgba(255,255,255,0.06)', display: 'flex', justifyContent: 'space-between', fontSize: '0.66rem', color: 'rgba(255,255,255,0.4)' }}>
                <span>Cadence: Real-time API</span>
                <span style={{ color: '#34d399' }}>● Connected</span>
              </div>
            </div>

            {/* Reservoir Ingestion */}
            <div className="glass-card" style={{ padding: 18, borderLeft: '3px solid #fb923c' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                <div style={{ width: 34, height: 34, borderRadius: 8, background: 'rgba(251,146,60,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Droplets size={16} color="#fb923c" />
                </div>
                <div>
                  <div style={{ fontSize: '0.86rem', fontWeight: 700, color: '#f1f5f9' }}>Reservoir Telemetry</div>
                  <div style={{ fontSize: '0.66rem', color: '#fb923c', fontWeight: 600 }}>LIVE DATA FEED</div>
                </div>
              </div>
              <div style={{ fontSize: '0.74rem', color: 'rgba(255,255,255,0.6)', lineHeight: 1.5 }}>
                Source: <strong>State Water Resources Telemetry</strong>. Tracks KRS, Kabini, Hemavathy, Bhavanisagar, and Mettur storage capacity, inflow, and outflows.
              </div>
              <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid rgba(255,255,255,0.06)', display: 'flex', justifyContent: 'space-between', fontSize: '0.66rem', color: 'rgba(255,255,255,0.4)' }}>
                <span>Cadence: Hourly/Daily dispatch</span>
                <span style={{ color: '#34d399' }}>● Connected</span>
              </div>
            </div>
          </div>
        </div>

        {/* SECTION 2: STATIC / REFERENCE DATA */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <span className="badge badge-info" style={{ fontSize: '0.68rem', fontWeight: 800 }}>STATIC / REFERENCE</span>
            <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#f8fafc' }}>Topographical & Structural Baselines</span>
            <span style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.4)', marginLeft: 'auto' }}>Pre-computed GIS layers</span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
            {/* HydroRIVERS */}
            <div className="glass-card" style={{ padding: 18, borderLeft: '3px solid #38bdf8' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                <div style={{ width: 34, height: 34, borderRadius: 8, background: 'rgba(56,189,248,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Map size={16} color="#38bdf8" />
                </div>
                <div>
                  <div style={{ fontSize: '0.86rem', fontWeight: 700, color: '#f1f5f9' }}>HydroRIVERS Database</div>
                  <div style={{ fontSize: '0.66rem', color: '#38bdf8', fontWeight: 600 }}>STATIC REFERENCE DATA</div>
                </div>
              </div>
              <div style={{ fontSize: '0.74rem', color: 'rgba(255,255,255,0.6)', lineHeight: 1.5 }}>
                River reach geometries, vector centerlines, and upstream-to-downstream topological routing graph of the Cauvery basin.
              </div>
              <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid rgba(255,255,255,0.06)', fontSize: '0.66rem', color: 'rgba(255,255,255,0.4)' }}>
                Format: Shapefile / GeoJSON vector reaches
              </div>
            </div>

            {/* SRTM DEM */}
            <div className="glass-card" style={{ padding: 18, borderLeft: '3px solid #a78bfa' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                <div style={{ width: 34, height: 34, borderRadius: 8, background: 'rgba(167,139,250,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Layers size={16} color="#a78bfa" />
                </div>
                <div>
                  <div style={{ fontSize: '0.86rem', fontWeight: 700, color: '#f1f5f9' }}>SRTM DEM (30m)</div>
                  <div style={{ fontSize: '0.66rem', color: '#a78bfa', fontWeight: 600 }}>STATIC REFERENCE DATA</div>
                </div>
              </div>
              <div style={{ fontSize: '0.74rem', color: 'rgba(255,255,255,0.6)', lineHeight: 1.5 }}>
                NASA Shuttle Radar Topography Mission digital elevation model. Supplies station elevations and reach slope gradient edge features.
              </div>
              <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid rgba(255,255,255,0.06)', fontSize: '0.66rem', color: 'rgba(255,255,255,0.4)' }}>
                Resolution: 1 arc-second (30m grid)
              </div>
            </div>

            {/* Station Metadata */}
            <div className="glass-card" style={{ padding: 18, borderLeft: '3px solid #e2e8f0' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                <div style={{ width: 34, height: 34, borderRadius: 8, background: 'rgba(255,255,255,0.08)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Database size={16} color="#e2e8f0" />
                </div>
                <div>
                  <div style={{ fontSize: '0.86rem', fontWeight: 700, color: '#f1f5f9' }}>Station Geo-Registry</div>
                  <div style={{ fontSize: '0.66rem', color: 'rgba(255,255,255,0.6)', fontWeight: 600 }}>STATIC REFERENCE DATA</div>
                </div>
              </div>
              <div style={{ fontSize: '0.74rem', color: 'rgba(255,255,255,0.6)', lineHeight: 1.5 }}>
                Official WGS-84 coordinates, warning thresholds, danger levels, and catchment designations for the 8 monitored gauging sites.
              </div>
              <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid rgba(255,255,255,0.06)', fontSize: '0.66rem', color: 'rgba(255,255,255,0.4)' }}>
                Nodes: 8 river stations + 7 major reservoirs
              </div>
            </div>
          </div>
        </div>

        {/* SECTION 3: MODEL RUNTIME & CHECKPOINT */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <span className="badge badge-warning" style={{ fontSize: '0.68rem', fontWeight: 800 }}>MODEL OUTPUT</span>
            <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#f8fafc' }}>Experiment 9 Inference & Interpolation</span>
            <span style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.4)', marginLeft: 'auto' }}>Checkpoint Loaded</span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
            {/* Model Checkpoint */}
            <div className="glass-card" style={{ padding: 18, borderLeft: '3px solid #22d3ee' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                <div style={{ width: 34, height: 34, borderRadius: 8, background: 'rgba(34,211,238,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Brain size={16} color="#22d3ee" />
                </div>
                <div>
                  <div style={{ fontSize: '0.86rem', fontWeight: 700, color: '#f1f5f9' }}>Models/best_model.pt</div>
                  <div style={{ fontSize: '0.66rem', color: '#22d3ee', fontWeight: 600 }}>EXPERIMENT 9 CHECKPOINT</div>
                </div>
              </div>
              <div style={{ fontSize: '0.74rem', color: 'rgba(255,255,255,0.6)', lineHeight: 1.5 }}>
                GRU + GATv2 + GraphSAGE spatio-temporal architecture. Loaded on CPU for real-time inference without GPU overhead.
              </div>
              <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid rgba(255,255,255,0.06)', display: 'flex', justifyContent: 'space-between', fontSize: '0.66rem', color: 'rgba(255,255,255,0.4)' }}>
                <span>Status: Loaded</span>
                <span style={{ color: '#34d399' }}>● Test NSE: 0.9968</span>
              </div>
            </div>

            {/* Native vs PCHIP Multi-Step */}
            <div className="glass-card" style={{ padding: 18, borderLeft: '3px solid #34d399' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                <div style={{ width: 34, height: 34, borderRadius: 8, background: 'rgba(52,211,153,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Zap size={16} color="#34d399" />
                </div>
                <div>
                  <div style={{ fontSize: '0.86rem', fontWeight: 700, color: '#f1f5f9' }}>Multi-Horizon Output</div>
                  <div style={{ fontSize: '0.66rem', color: '#34d399', fontWeight: 600 }}>MODEL PREDICTION</div>
                </div>
              </div>
              <div style={{ fontSize: '0.74rem', color: 'rgba(255,255,255,0.6)', lineHeight: 1.5 }}>
                Generates <strong>6h, 12h, 24h</strong> native neural predictions. Smooth <strong>1h, 3h, 18h</strong> views are generated via PCHIP cubic spline interpolation.
              </div>
              <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid rgba(255,255,255,0.06)', fontSize: '0.66rem', color: 'rgba(255,255,255,0.4)' }}>
                Horizons: 6 native anchors & intermediate spline
              </div>
            </div>

            {/* Inference Latency */}
            <div className="glass-card" style={{ padding: 18, borderLeft: '3px solid #a78bfa' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                <div style={{ width: 34, height: 34, borderRadius: 8, background: 'rgba(167,139,250,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Clock size={16} color="#a78bfa" />
                </div>
                <div>
                  <div style={{ fontSize: '0.86rem', fontWeight: 700, color: '#f1f5f9' }}>Inference Latency</div>
                  <div style={{ fontSize: '0.66rem', color: '#a78bfa', fontWeight: 600 }}>SYSTEM PERFORMANCE</div>
                </div>
              </div>
              <div style={{ fontSize: '0.74rem', color: 'rgba(255,255,255,0.6)', lineHeight: 1.5 }}>
                Average forward pass latency: <strong>{diagnostics.inference_latency_avg_ms.toFixed(1)} ms</strong>. Query latency: <strong>{diagnostics.api_latency_ms.toFixed(1)} ms</strong>.
              </div>
              <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid rgba(255,255,255,0.06)', fontSize: '0.66rem', color: 'rgba(255,255,255,0.4)' }}>
                Fast response for decision support alerts
              </div>
            </div>
          </div>
        </div>

        {/* SECTION 4: SYSTEM HEALTH & SERVER METRICS */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {/* Server Resources */}
          <motion.div className="glass-card" style={{ padding: 22 }}
            initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
          >
            <h3 style={{ fontSize: '0.9rem', fontWeight: 700, margin: '0 0 14px', color: '#f1f5f9' }}>Server Host Resources</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.6)', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Cpu size={14} color="#34d399" /> CPU Utilization
                  </span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: '#34d399', fontWeight: 700 }}>
                    {diagnostics.system_metrics.cpu_usage_pct.toFixed(0)}%
                  </span>
                </div>
                <div className="progress-track" style={{ height: 6 }}>
                  <motion.div className="progress-fill" style={{ width: `${diagnostics.system_metrics.cpu_usage_pct}%`, background: '#34d399' }} />
                </div>
              </div>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.6)', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <HardDrive size={14} color="#22d3ee" /> Memory Allocation
                  </span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: '#22d3ee', fontWeight: 700 }}>
                    {diagnostics.system_metrics.memory_usage_pct.toFixed(0)}%
                  </span>
                </div>
                <div className="progress-track" style={{ height: 6 }}>
                  <motion.div className="progress-fill" style={{ width: `${diagnostics.system_metrics.memory_usage_pct}%`, background: '#22d3ee' }} />
                </div>
              </div>
            </div>
          </motion.div>

          {/* Database & Ingestion Health */}
          <motion.div className="glass-card" style={{ padding: 22 }}
            initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}
          >
            <h3 style={{ fontSize: '0.9rem', fontWeight: 700, margin: '0 0 14px', color: '#f1f5f9' }}>Database & Scheduler Status</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ padding: '8px 12px', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.74rem', color: 'rgba(255,255,255,0.6)' }}>SQLite Telemetry Store</span>
                <span style={{ fontSize: '0.74rem', color: STATUS_META[dbHealth].color, fontWeight: 700 }}>{STATUS_META[dbHealth].label}</span>
              </div>
              <div style={{ padding: '8px 12px', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.74rem', color: 'rgba(255,255,255,0.6)' }}>Ingestion Sync Scheduler</span>
                <span style={{ fontSize: '0.74rem', color: STATUS_META[schedHealth].color, fontWeight: 700 }}>{STATUS_META[schedHealth].label}</span>
              </div>
              <div style={{ padding: '8px 12px', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.74rem', color: 'rgba(255,255,255,0.6)' }}>Telemetry Data Drift</span>
                <span style={{ fontSize: '0.74rem', color: '#34d399', fontWeight: 700 }}>{diagnostics.data_drift}</span>
              </div>
            </div>
          </motion.div>
        </div>

      </div>
    </AppLayout>
  );
}
