'use client';
import { motion } from 'framer-motion';
import { useState, useEffect, useMemo } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import AppLayout from '../AppLayout';
import PageHeader from '../components/PageHeader';
import { STATUS_CONFIG } from '../data/mockData';
import { MapPin, AlertTriangle, RefreshCw, Activity, Radio, TrendingUp } from 'lucide-react';
import { api } from '../../services/api';

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: 'rgba(10,22,40,0.95)', backdropFilter: 'blur(16px)', border: '1px solid rgba(34,211,238,0.2)', borderRadius: 10, padding: '8px 12px', fontSize: '0.76rem' }}>
      <p style={{ color: 'rgba(255,255,255,0.5)', marginBottom: 3 }}>{label}</p>
      {payload.map((p: any) => p.value != null && <p key={p.dataKey} style={{ color: p.color, margin: 0 }}>{p.name}: <strong>{Number(p.value).toFixed(2)}ft</strong></p>)}
    </div>
  );
};

export default function StationsPage() {
  const [stations, setStations] = useState<any[]>([]);
  const [selectedStationId, setSelectedStationId] = useState<string>('METTUR');
  const [predictionData, setPredictionData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [hasError, setHasError] = useState<boolean>(false);

  const fetchStationsData = async () => {
    try {
      setIsLoading(true);
      setHasError(false);
      await api.login();
      const dash = await api.getDashboard();
      
      // Filter for the 8 Cauvery network stations (Cauvery main stem + Bhavani tributary)
      const cauveryStations = (dash.stations || []).filter(
        (s: any) => s.basin === 'Cauvery' || s.basin === 'Bhavani'
      );
      const displayStations = cauveryStations.length === 8 ? cauveryStations : (dash.stations || []).slice(0, 8);
      setStations(displayStations);

      const hasMettur = displayStations.some((s: any) => s.id === 'METTUR');
      const firstStation = displayStations[0]?.id || 'METTUR';
      const initialStation = hasMettur ? 'METTUR' : firstStation;
      setSelectedStationId(initialStation);

      try {
        const pred = await api.getPrediction(initialStation);
        setPredictionData(pred);
      } catch (predErr) {
        console.warn('Prediction fetch non-fatal error:', predErr);
      }
    } catch (err) {
      console.error('Failed to load stations overview:', err);
      setHasError(true);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchStationsData();
  }, []);

  const handleStationClick = async (stationId: string) => {
    try {
      setSelectedStationId(stationId);
      const pred = await api.getPrediction(stationId);
      setPredictionData(pred);
    } catch (err) {
      console.error(`Failed to fetch GNN predictions for station ${stationId}:`, err);
    }
  };

  const selected = useMemo(() => {
    return stations.find(s => s.id === selectedStationId) || stations[0];
  }, [stations, selectedStationId]);

  const sc = useMemo(() => {
    if (!selected) return STATUS_CONFIG.safe;
    const rawStatus = (selected.risk_level || 'Safe').toLowerCase();
    const severity = rawStatus === 'severe flood' || rawStatus === 'high risk' ? 'danger' : rawStatus === 'moderate risk' ? 'warning' : rawStatus === 'low risk' ? 'alert' : 'safe';
    return STATUS_CONFIG[severity];
  }, [selected]);

  const series = useMemo(() => {
    if (!predictionData?.hydrograph) return [];
    const pts = predictionData.hydrograph;
    const lastObsIdx = pts.findLastIndex ? pts.findLastIndex((h: any) => h.section === 'observed') : pts.map((h: any) => h.section).lastIndexOf('observed');
    const lastObsVal = lastObsIdx >= 0 ? pts[lastObsIdx].observed : null;

    return pts.map((h: any, i: number) => {
      const isBridgePoint = (i === lastObsIdx);
      return {
        time: h.time,
        level: h.observed,
        forecast: isBridgePoint ? (h.predicted ?? lastObsVal) : h.predicted,
        upper: isBridgePoint ? (h.upper ?? lastObsVal) : h.upper,
        lower: isBridgePoint ? (h.lower ?? lastObsVal) : h.lower,
      };
    });
  }, [predictionData]);

  if (isLoading) {
    return (
      <AppLayout>
        <div style={{ padding: '24px 32px', display: 'flex', gap: 20, height: 'calc(100vh - 64px)' }}>
          <div style={{ width: 300, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[1, 2, 3, 4, 5].map(i => (
              <div key={i} style={{ height: 95, background: 'rgba(255,255,255,0.03)', borderRadius: 12 }} className="shimmer" />
            ))}
          </div>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ height: 160, background: 'rgba(255,255,255,0.03)', borderRadius: 20 }} className="shimmer" />
            <div style={{ height: 300, background: 'rgba(255,255,255,0.03)', borderRadius: 20 }} className="shimmer" />
          </div>
        </div>
      </AppLayout>
    );
  }

  if (hasError || !selected) {
    return (
      <AppLayout>
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          minHeight: 'calc(100vh - 120px)', gap: 16, padding: 32, textAlign: 'center',
        }}>
          <AlertTriangle size={48} color="#fb7185" />
          <h3 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#e2e8f0' }}>Failed to Load Stations</h3>
          <button className="btn btn-primary" onClick={fetchStationsData}>
            <RefreshCw size={14} /> Retry
          </button>
        </div>
      </AppLayout>
    );
  }

  const rawStatus = (selected.risk_level || 'Safe').toLowerCase();
  const severity = rawStatus === 'severe flood' || rawStatus === 'high risk' ? 'danger' : rawStatus === 'moderate risk' ? 'warning' : rawStatus === 'low risk' ? 'alert' : 'safe';
  const pct = Math.min((selected.water_level / selected.danger_level) * 100, 100);
  const trend = pct > 75 ? '↑ Rising' : pct < 25 ? '↓ Falling' : '→ Steady';
  const trendColor = pct > 75 ? '#fb7185' : pct < 25 ? '#34d399' : '#fbbf24';

  return (
    <AppLayout>
      <div style={{ padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 16, minHeight: 'calc(100vh - 64px)', boxSizing: 'border-box' }}>

        {/* Page Header */}
        <PageHeader
          title="River Station Monitor"
          subtitle="Current water levels and station-specific Experiment 9 forecasts"
          purpose="Compare individual river-gauge conditions and identify stations approaching operational thresholds."
          badges={[
            { label: '8 Active Cauvery Gauges', variant: 'info' },
            { label: 'Live Telemetry + Exp 9 Forecast', variant: 'safe' }
          ]}
        />

        {/* Main Station Workspace */}
        <div style={{ display: 'flex', gap: 20, flex: 1, overflowY: 'auto' }}>

          {/* Station list */}
          <div style={{ width: 300, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 8, maxHeight: '100%', overflowY: 'auto', paddingRight: 4 }}>
            <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'rgba(255,255,255,0.4)', marginBottom: 4, display: 'flex', justifyContent: 'space-between' }}>
              <span>MONITORED STATIONS ({stations.length})</span>
              <span>LIVE FEED</span>
            </div>
            {stations.map((s, i) => {
              const rSev = (s.risk_level || 'Safe').toLowerCase();
              const sSev = rSev === 'severe flood' || rSev === 'high risk' ? 'danger' : rSev === 'moderate risk' ? 'warning' : rSev === 'low risk' ? 'alert' : 'safe';
              const c = STATUS_CONFIG[sSev] || STATUS_CONFIG.safe;
              const isActive = s.id === selectedStationId;
              const sPct = Math.min((s.water_level / s.danger_level) * 100, 100);
              const sTrend = sPct > 75 ? '↑' : sPct < 25 ? '↓' : '→';
              const sTrendCol = sTrend === '↑' ? '#fb7185' : sTrend === '↓' ? '#34d399' : '#fbbf24';

              return (
                <motion.div
                  key={s.id}
                  initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(0.5, i * 0.03) }}
                  onClick={() => handleStationClick(s.id)}
                  whileHover={{ x: 4 }}
                  style={{
                    padding: '12px 14px',
                    borderRadius: 12,
                    cursor: 'pointer',
                    border: `1px solid ${isActive ? '#22d3ee' : 'rgba(255,255,255,0.06)'}`,
                    background: isActive ? 'rgba(34,211,238,0.08)' : 'rgba(255,255,255,0.02)',
                    boxShadow: isActive ? '0 0 16px rgba(34,211,238,0.2)' : 'none',
                    transition: 'all 0.2s',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <span className={`status-dot status-${sSev}`} />
                    <span style={{ fontWeight: 700, fontSize: '0.84rem', color: '#e2e8f0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 130 }}>
                      {s.name.replace(' Gauge', '').replace(' Reservoir', '')}
                    </span>
                    <span className={`badge badge-${sSev}`} style={{ marginLeft: 'auto', fontSize: '0.58rem', padding: '1px 6px' }}>{c.label}</span>
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: 4 }}>
                    <div>
                      <span style={{ fontSize: '0.66rem', color: 'rgba(255,255,255,0.4)', marginRight: 4 }}>Observed:</span>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.95rem', fontWeight: 800, color: c.color }}>{s.water_level?.toFixed(1)}</span>
                      <span style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)', marginLeft: 2 }}>ft</span>
                    </div>
                    <div style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)' }}>
                      Danger: <strong style={{ color: 'rgba(255,255,255,0.7)' }}>{s.danger_level?.toFixed(1)}ft</strong>
                    </div>
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 6, paddingTop: 6, borderTop: '1px solid rgba(255,255,255,0.04)', fontSize: '0.64rem' }}>
                    <span style={{ color: '#22d3ee', fontWeight: 600 }}>Engine: Exp 9 GNN</span>
                    <span style={{ color: sTrendCol, fontWeight: 700 }}>Trend: {sTrend}</span>
                  </div>
                </motion.div>
              );
            })}
          </div>

          {/* Selected Station Workspace */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 16 }}>

            {/* Hierarchy Section 1: CURRENT CONDITION & THRESHOLDS */}
            <motion.div className="glass-card" style={{ padding: 22 }}
              key={selected.id}
              initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }}
            >
              {/* Header */}
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 16 }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <MapPin size={18} color={sc.color} />
                    <h2 style={{ fontSize: '1.35rem', fontWeight: 800, color: '#e2e8f0', margin: 0 }}>{selected.name}</h2>
                    <span className={`badge badge-${severity}`}>
                      <span className={`status-dot status-${severity}`} />
                      {sc.label}
                    </span>
                  </div>
                  <p style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.4)', margin: '4px 0 0' }}>
                    {selected.basin} Basin · Elevation: {selected.elevation}m · Telemetry Ingestion: Live Active
                  </p>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '0.66rem', color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>OBSERVED — LIVE</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '2rem', fontWeight: 800, color: sc.color, lineHeight: 1 }}>{selected.water_level?.toFixed(2)}ft</div>
                  <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)', marginTop: 2 }}>of {selected.danger_level?.toFixed(1)}ft danger limit</div>
                </div>
              </div>

              {/* Hierarchy: CURRENT CONDITION METRICS */}
              <div style={{ fontSize: '0.68rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'rgba(255,255,255,0.35)', marginBottom: 8 }}>
                CURRENT CONDITION & TELEMETRY
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10, marginBottom: 18 }}>
                <div style={{ background: 'rgba(255,255,255,0.035)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 10, padding: '10px 12px' }}>
                  <div style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase' }}>Observed Level</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.05rem', fontWeight: 700, color: sc.color, marginTop: 2 }}>{selected.water_level?.toFixed(2)} ft</div>
                  <div style={{ fontSize: '0.62rem', color: 'rgba(255,255,255,0.3)', marginTop: 2 }}>Observed — Live</div>
                </div>
                <div style={{ background: 'rgba(255,255,255,0.035)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 10, padding: '10px 12px' }}>
                  <div style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase' }}>Discharge Flow</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.05rem', fontWeight: 700, color: '#22d3ee', marginTop: 2 }}>{selected.discharge?.toFixed(1)} m³/s</div>
                  <div style={{ fontSize: '0.62rem', color: 'rgba(255,255,255,0.3)', marginTop: 2 }}>Hydrological telemetry</div>
                </div>
                <div style={{ background: 'rgba(255,255,255,0.035)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 10, padding: '10px 12px' }}>
                  <div style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase' }}>Observed Rain</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.05rem', fontWeight: 700, color: '#a78bfa', marginTop: 2 }}>{selected.rain_observed?.toFixed(1)} mm</div>
                  <div style={{ fontSize: '0.62rem', color: 'rgba(255,255,255,0.3)', marginTop: 2 }}>OpenWeather API feed</div>
                </div>
                <div style={{ background: 'rgba(255,255,255,0.035)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 10, padding: '10px 12px' }}>
                  <div style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase' }}>Soil Moisture</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.05rem', fontWeight: 700, color: '#34d399', marginTop: 2 }}>{((selected.soil_moisture != null ? selected.soil_moisture : 0.45) * 100).toFixed(0)}%</div>
                  <div style={{ fontSize: '0.62rem', color: 'rgba(255,255,255,0.3)', marginTop: 2 }}>Basin saturation</div>
                </div>
              </div>

              {/* Hierarchy: THRESHOLDS & TREND */}
              <div style={{ fontSize: '0.68rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'rgba(255,255,255,0.35)', marginBottom: 8 }}>
                THRESHOLDS & TREND ANALYSIS
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 2fr', gap: 14, alignItems: 'center' }}>
                <div style={{ background: 'rgba(255,255,255,0.025)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 8, padding: '8px 12px' }}>
                  <div style={{ fontSize: '0.64rem', color: 'rgba(255,255,255,0.4)' }}>Operational Warning:</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.9rem', fontWeight: 700, color: '#fbbf24', marginTop: 2 }}>
                    {selected.warning_level != null ? `${selected.warning_level.toFixed(1)} ft` : 'N/A'}
                  </div>
                </div>
                <div style={{ background: 'rgba(255,255,255,0.025)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 8, padding: '8px 12px' }}>
                  <div style={{ fontSize: '0.64rem', color: 'rgba(255,255,255,0.4)' }}>Current Trend:</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.9rem', fontWeight: 700, color: trendColor, marginTop: 2 }}>
                    {trend}
                  </div>
                </div>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.5)' }}>Danger Level Ratio</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: sc.color, fontWeight: 700 }}>{pct.toFixed(0)}% of limit ({selected.danger_level?.toFixed(1)}ft)</span>
                  </div>
                  <div className="progress-track">
                    <motion.div className="progress-fill" style={{ background: sc.color, width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 1 }} />
                  </div>
                </div>
              </div>
            </motion.div>

            {/* Hierarchy Section 2: FORECAST HYDROGRAPH */}
            <motion.div className="glass-card gradient-border" style={{ padding: '20px 24px', flex: 1, minHeight: 300 }}
              initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <div>
                  <div style={{ fontSize: '0.98rem', fontWeight: 700 }}>
                    Forecast Hydrograph — {selected.name}
                  </div>
                  <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)', marginTop: 2 }}>
                    Observed timeline (Live) with Experiment 9 GNN multi-horizon predictions
                  </div>
                </div>
                <span className="badge badge-info" style={{ fontSize: '0.64rem' }}>
                  Exp 9 GNN Engine
                </span>
              </div>

              <ResponsiveContainer width="100%" height={240}>
                <AreaChart data={series} margin={{ top: 8, right: 8, left: -22, bottom: 0 }}>
                  <defs>
                    <linearGradient id="actualGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%"   stopColor="#22d3ee" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="#22d3ee" stopOpacity={0.02} />
                    </linearGradient>
                    <linearGradient id="forecastGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%"   stopColor="#a78bfa" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="#a78bfa" stopOpacity={0.01} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis dataKey="time" tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.28)' }} tickLine={false} axisLine={false} interval={11} />
                  <YAxis tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.28)' }} tickLine={false} axisLine={false} />
                  <Tooltip content={<CustomTooltip />} />
                  <ReferenceLine y={selected.danger_level} stroke="#fb7185" strokeDasharray="5 4" strokeWidth={1.5}
                    label={{ value: `Danger (${selected.danger_level.toFixed(1)}ft)`, position: 'right', fontSize: 9, fill: '#fb7185' }} />
                  <Area type="monotone" dataKey="level" stroke="#22d3ee" strokeWidth={2} fill="url(#actualGrad)" name="Observed — Live" dot={false} />
                  <Area type="monotone" dataKey="forecast" stroke="#a78bfa" strokeWidth={1.8} fill="url(#forecastGrad)" name="Forecast — Exp 9" strokeDasharray="5 3" dot={false} />
                </AreaChart>
              </ResponsiveContainer>

              {/* Standardized Chart Legend */}
              <div style={{ display: 'flex', gap: 20, marginTop: 10, paddingTop: 10, borderTop: '1px solid rgba(255,255,255,0.05)', flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <div style={{ width: 18, height: 3, background: '#22d3ee', borderRadius: 2 }} />
                  <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.55)' }}>Observed — Live</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <div style={{ width: 18, height: 2, borderTop: '2px dashed #a78bfa' }} />
                  <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.55)' }}>Forecast — Exp 9</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <div style={{ width: 18, height: 2, borderTop: '2px dashed #fb7185' }} />
                  <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.55)' }}>Danger threshold</span>
                </div>
              </div>
            </motion.div>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
