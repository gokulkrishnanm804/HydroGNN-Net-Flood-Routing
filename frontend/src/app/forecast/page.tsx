'use client';
import { motion, AnimatePresence } from 'framer-motion';
import { useState, useEffect, useMemo } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts';
import AppLayout from '../AppLayout';
import { STATUS_CONFIG } from '../data/mockData';
import { TrendingUp, Clock, ChevronDown, AlertTriangle, Brain, RefreshCw } from 'lucide-react';
import { api } from '../../services/api';

const HORIZONS_META = [
  { h: 1,  label: '1h',  confidence: 97, color: '#34d399', desc: 'Near-real-time'    },
  { h: 3,  label: '3h',  confidence: 94, color: '#22d3ee', desc: 'Short-term'         },
  { h: 6,  label: '6h',  confidence: 89, color: '#06b6d4', desc: 'Operational'        },
  { h: 12, label: '12h', confidence: 84, color: '#a78bfa', desc: 'Medium-range'       },
  { h: 18, label: '18h', confidence: 77, color: '#fb923c', desc: 'Extended'           },
  { h: 24, label: '24h', confidence: 71, color: '#fb7185', desc: 'Long-range'         },
];

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: 'rgba(8,18,40,0.96)', backdropFilter: 'blur(20px)',
      border: '1px solid rgba(34,211,238,0.2)', borderRadius: 12,
      padding: '10px 14px', fontSize: '0.78rem', boxShadow: '0 16px 48px rgba(0,0,0,0.7)',
    }}>
      <p style={{ color: 'rgba(255,255,255,0.4)', marginBottom: 5, fontSize: '0.7rem' }}>{label}</p>
      {payload.map((p: any) => p.value != null && (
        <p key={p.dataKey} style={{ color: p.color, display: 'flex', justifyContent: 'space-between', gap: 16, marginBottom: 2 }}>
          <span>{p.name}</span><strong>{Number(p.value).toFixed(2)}ft</strong>
        </p>
      ))}
    </div>
  );
};

export default function ForecastPage() {
  const [stations, setStations] = useState<any[]>([]);
  const [selectedStation, setSelectedStation] = useState('METTUR');
  const [activeHorizon, setActiveHorizon] = useState(6);
  const [showDropdown, setShowDropdown] = useState(false);
  const [predictionData, setPredictionData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [hasError, setHasError] = useState<boolean>(false);

  const fetchInitialData = async () => {
    try {
      setIsLoading(true);
      setHasError(false);
      await api.login();
      const dash = await api.getDashboard();
      const uniqueStations = Array.from(
        new Map((dash.stations || []).map((s: any) => [s.id, s])).values()
      );
      setStations(uniqueStations);
      
      const hasMettur = uniqueStations.some((s: any) => s.id === 'METTUR');
      const initialStation = hasMettur ? 'METTUR' : (uniqueStations[0]?.id || 'METTUR');
      setSelectedStation(initialStation);
      
      const pred = await api.getPrediction(initialStation, [1, 3, 6, 12, 18, 24]);
      setPredictionData(pred);
    } catch (err) {
      console.error('Failed to load forecast data:', err);
      setHasError(true);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchInitialData();
  }, []);

  const handleStationChange = async (stationId: string) => {
    try {
      setSelectedStation(stationId);
      setShowDropdown(false);
      const pred = await api.getPrediction(stationId, [1, 3, 6, 12, 18, 24]);
      setPredictionData(pred);
    } catch (err) {
      console.error(`Failed to fetch GNN predictions for station ${stationId}:`, err);
    }
  };

  const station = useMemo(() => {
    return stations.find(s => s.id === selectedStation) || stations[0];
  }, [stations, selectedStation]);

  const sc = useMemo(() => {
    if (!station) return STATUS_CONFIG.safe;
    const rawStatus = (station.risk_level || 'Safe').toLowerCase();
    const severity = rawStatus === 'severe flood' || rawStatus === 'high risk' ? 'danger' : rawStatus === 'moderate risk' ? 'warning' : rawStatus === 'low risk' ? 'alert' : 'safe';
    return STATUS_CONFIG[severity];
  }, [station]);

  const hMeta = useMemo(() => {
    return HORIZONS_META.find(h => h.h === activeHorizon) || HORIZONS_META[2];
  }, [activeHorizon]);

  // conformed series mapping
  const series = useMemo(() => {
    if (!predictionData?.hydrograph) return [];
    return predictionData.hydrograph.map((h: any) => ({
      label: h.time,
      level: h.observed,
      forecast: h.predicted,
      upper: h.upper,
      lower: h.lower
    }));
  }, [predictionData]);

  const predictedPeak = useMemo(() => {
    if (!predictionData?.predictions) return 0.0;
    const matched = predictionData.predictions.find((p: any) => p.horizon_hours === activeHorizon);
    return matched ? matched.level_m : (station?.water_level || 0.0) + 1.2;
  }, [predictionData, activeHorizon, station]);

  const hoursToThreshold = useMemo(() => {
    if (!station) return 0;
    return station.danger_level > station.water_level
      ? Math.round((station.danger_level - station.water_level) / 0.22)
      : 0;
  }, [station]);

  if (isLoading) {
    return (
      <AppLayout>
        <div style={{ padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div style={{ height: 60, background: 'rgba(255,255,255,0.03)', borderRadius: 16 }} className="shimmer" />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 10 }}>
            {[1, 2, 3, 4, 5, 6].map(i => (
              <div key={i} style={{ height: 80, background: 'rgba(255,255,255,0.03)', borderRadius: 16 }} className="shimmer" />
            ))}
          </div>
          <div style={{ height: 320, background: 'rgba(255,255,255,0.03)', borderRadius: 20 }} className="shimmer" />
        </div>
      </AppLayout>
    );
  }

  if (hasError || !station) {
    return (
      <AppLayout>
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          minHeight: 'calc(100vh - 120px)', gap: 16, padding: 32, textAlign: 'center',
        }}>
          <AlertTriangle size={48} color="#fb7185" />
          <h3 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#e2e8f0' }}>No Forecast Data Available</h3>
          <button className="btn btn-primary" onClick={fetchInitialData}>
            <RefreshCw size={14} /> Retry
          </button>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="page-content">

        {/* Hero bar */}
        <motion.div className="glass-card gradient-border" style={{ padding: '20px 28px', overflow: 'visible', zIndex: 50 }}
          initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
            <div className="ring-spinner" style={{ width: 48, height: 48, flexShrink: 0 }}>
              <Brain size={18} color="#22d3ee" />
            </div>
            <div>
              <div style={{ fontSize: '1.1rem', fontWeight: 800, letterSpacing: '-0.02em' }}>Multi-Horizon Flood Forecast</div>
              <div style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.4)', marginTop: 2 }}>
                HydroGNN-Net · GRU → GATv2 → GraphSAGE · Ensemble mean prediction
              </div>
            </div>

            {/* Station selector */}
            <div style={{ marginLeft: 'auto', position: 'relative' }}>
              <motion.button
                className="btn btn-ghost"
                style={{ fontSize: '0.82rem', padding: '8px 16px', gap: 8 }}
                onClick={() => setShowDropdown(d => !d)}
                whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.95 }}
              >
                <span className={`status-dot status-${sc.label.toLowerCase() === 'safe' ? 'safe' : sc.label.toLowerCase() === 'warning' ? 'warning' : 'danger'}`} style={{ width: 7, height: 7 }} />
                {station.name}
                <motion.div animate={{ rotate: showDropdown ? 180 : 0 }} transition={{ duration: 0.2 }}>
                  <ChevronDown size={14} />
                </motion.div>
              </motion.button>

              <AnimatePresence>
                {showDropdown && (
                  <motion.div
                    initial={{ opacity: 0, y: -8, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -8, scale: 0.95 }}
                    style={{
                      position: 'absolute', top: 'calc(100% + 8px)', right: 0, zIndex: 200,
                      background: 'rgba(8,18,40,0.98)', backdropFilter: 'blur(24px)',
                      border: '1px solid rgba(255,255,255,0.1)', borderRadius: 14, overflow: 'hidden',
                      boxShadow: '0 20px 60px rgba(0,0,0,0.7)', minWidth: 220,
                      maxHeight: 300, overflowY: 'auto'
                    }}
                  >
                    {stations.map(s => {
                      const rawStatus = (s.risk_level || 'Safe').toLowerCase();
                      const severity = rawStatus === 'severe flood' || rawStatus === 'high risk' ? 'danger' : rawStatus === 'moderate risk' ? 'warning' : rawStatus === 'low risk' ? 'alert' : 'safe';
                      const ssc = STATUS_CONFIG[severity];
                      return (
                        <motion.div key={s.id}
                          onClick={() => handleStationChange(s.id)}
                          whileHover={{ background: 'rgba(34,211,238,0.05)' }}
                          style={{
                            padding: '10px 16px', cursor: 'pointer',
                            borderBottom: '1px solid rgba(255,255,255,0.04)',
                            display: 'flex', alignItems: 'center', gap: 10,
                            background: selectedStation === s.id ? 'rgba(34,211,238,0.06)' : 'transparent',
                          }}
                        >
                          <span className={`status-dot status-${severity}`} style={{ width: 7, height: 7 }} />
                          <span style={{ fontSize: '0.82rem', color: selectedStation === s.id ? '#22d3ee' : 'rgba(255,255,255,0.75)', fontWeight: selectedStation === s.id ? 600 : 400 }}>
                            {s.name.replace(' Gauge', '').replace(' Reservoir', '')}
                          </span>
                          <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: ssc.color }}>{s.water_level.toFixed(1)}ft</span>
                        </motion.div>
                      );
                    })}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </motion.div>

        {/* Horizon selector */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 10 }}>
          {HORIZONS_META.map((hm, i) => (
            <motion.button
              key={hm.h}
              onClick={() => setActiveHorizon(hm.h)}
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 + i * 0.06 }}
              whileHover={{ y: -3 }} whileTap={{ scale: 0.94 }}
              style={{
                background: activeHorizon === hm.h ? `${hm.color}18` : 'rgba(10,22,50,0.6)',
                border: `1.5px solid ${activeHorizon === hm.h ? hm.color + '50' : 'rgba(255,255,255,0.07)'}`,
                borderRadius: 14, padding: '14px 12px', cursor: 'pointer', textAlign: 'center',
                boxShadow: activeHorizon === hm.h ? `0 0 20px ${hm.color}30` : 'none',
                backdropFilter: 'blur(16px)', transition: 'all 0.2s',
              }}
            >
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.3rem', fontWeight: 800, color: activeHorizon === hm.h ? hm.color : 'rgba(255,255,255,0.5)', lineHeight: 1 }}>
                {hm.label}
              </div>
              <div style={{ fontSize: '0.62rem', color: 'rgba(255,255,255,0.35)', marginTop: 5, textTransform: 'uppercase', letterSpacing: '0.07em' }}>
                {hm.desc}
              </div>
              <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'center' }}>
                <div style={{ flex: 1, height: 3, background: 'rgba(255,255,255,0.08)', borderRadius: 2, overflow: 'hidden' }}>
                  <motion.div
                    style={{ height: '100%', background: hm.color, borderRadius: 2, width: 0 }}
                    animate={{ width: `${hm.confidence}%` }}
                    transition={{ delay: 0.3 + i * 0.06, duration: 1 }}
                  />
                </div>
                <span style={{ fontSize: '0.62rem', color: hm.color, fontWeight: 700, whiteSpace: 'nowrap' }}>{hm.confidence}%</span>
              </div>
            </motion.button>
          ))}
        </div>

        {/* Main chart */}
        <motion.div className="glass-card gradient-border" style={{ padding: '24px 28px' }}
          initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
            <div>
              <div style={{ fontSize: '1rem', fontWeight: 700, letterSpacing: '-0.02em', display: 'flex', alignItems: 'center', gap: 10 }}>
                {station.name}
                <span className={`badge badge-${sc.label.toLowerCase() === 'safe' ? 'safe' : sc.label.toLowerCase() === 'warning' ? 'warning' : 'danger'}`} style={{ fontSize: '0.62rem' }}>
                  <span className={`status-dot status-${sc.label.toLowerCase() === 'safe' ? 'safe' : sc.label.toLowerCase() === 'warning' ? 'warning' : 'danger'}`} style={{ width: 5, height: 5 }} />
                  {sc.label}
                </span>
              </div>
              <div style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.38)', marginTop: 3 }}>
                {activeHorizon}-hour forecast · Confidence: {hMeta.confidence}% · Soil Moisture: {predictionData?.routing_metadata?.soil_moisture || 0.4}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.6rem', fontWeight: 800, color: sc.color, lineHeight: 1 }}>{station.water_level?.toFixed(2)}ft</div>
                <div style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.35)', marginTop: 2 }}>Current level</div>
              </div>
              <div style={{ width: 1, height: 36, background: 'rgba(255,255,255,0.08)' }} />
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.6rem', fontWeight: 800, color: hMeta.color, lineHeight: 1 }}>{predictedPeak?.toFixed(2)}ft</div>
                <div style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.35)', marginTop: 2 }}>Predicted peak (+{activeHorizon}h)</div>
              </div>
            </div>
          </div>

          <ResponsiveContainer width="100%" height={320}>
            <AreaChart data={series} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
              <defs>
                <linearGradient id="actualGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%"   stopColor="#22d3ee" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="#22d3ee" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="forecastGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={hMeta.color} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={hMeta.color} stopOpacity={0.01} />
                </linearGradient>
                <linearGradient id="ciGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={hMeta.color} stopOpacity={0.12} />
                  <stop offset="100%" stopColor={hMeta.color} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.28)' }} tickLine={false} axisLine={false} interval={11} />
              <YAxis tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.28)' }} tickLine={false} axisLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine y={station.danger_level} stroke="#fb7185" strokeDasharray="6 4" strokeWidth={1.5}
                label={{ value: `Danger ${station.danger_level.toFixed(1)}ft`, position: 'right', fontSize: 9, fill: '#fb7185' }} />

              {/* Confidence interval */}
              <Area type="monotone" dataKey="upper" stroke="none" fill="url(#ciGrad)" name="Upper CI (ft)" />
              <Area type="monotone" dataKey="lower" stroke="none" fill="white" fillOpacity={0.01} name="Lower CI (ft)" />

              {/* Observed */}
              <Area type="monotone" dataKey="level" stroke="#22d3ee" strokeWidth={2.5}
                fill="url(#actualGrad)" dot={false} name="Observed (ft)"
                animationDuration={1800} animationEasing="ease-out" />

              {/* Forecast */}
              <Area type="monotone" dataKey="forecast" stroke={hMeta.color} strokeWidth={2.2}
                fill="url(#forecastGrad)" dot={false} name={`${activeHorizon}h Forecast (ft)`}
                strokeDasharray="7 3" animationDuration={2000} />
            </AreaChart>
          </ResponsiveContainer>

          {/* Legend */}
          <div style={{ display: 'flex', gap: 20, marginTop: 12, paddingTop: 12, borderTop: '1px solid rgba(255,255,255,0.05)' }}>
            {[
              { color: '#22d3ee', label: 'Observed', solid: true },
              { color: hMeta.color, label: `${activeHorizon}h AI Forecast`, solid: false },
              { color: '#fb7185', label: 'Danger Threshold', solid: false },
            ].map(l => (
              <div key={l.label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <div style={{ width: 22, height: 2, background: l.color, borderRadius: 2, border: l.solid ? 'none' : `1px dashed ${l.color}` }} />
                <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.45)' }}>{l.label}</span>
              </div>
            ))}
          </div>
        </motion.div>

        {/* Alert */}
        {(sc.label.toLowerCase() === 'warning' || sc.label.toLowerCase() === 'danger') && (
          <motion.div
            style={{ background: 'rgba(251,113,133,0.08)', border: '1px solid rgba(251,113,133,0.2)', borderRadius: 14, padding: '14px 20px', display: 'flex', alignItems: 'flex-start', gap: 12 }}
            initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }}
          >
            <motion.div animate={{ rotate: [0, -8, 8, -5, 5, 0] }} transition={{ duration: 1, repeat: Infinity, repeatDelay: 4 }}>
              <AlertTriangle size={18} color="#fb7185" />
            </motion.div>
            <div>
              <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#fb7185', marginBottom: 4 }}>High Risk Warning — {station.name}</div>
              <p style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.6)', margin: 0, lineHeight: 1.6 }}>
                AI forecast indicates danger threshold breach in approximately <strong style={{ color: '#fb7185' }}>{hoursToThreshold} hours</strong> at {activeHorizon}h confidence ({hMeta.confidence}%).
                Downstream communities should be placed on pre-emptive alert.
              </p>
            </div>
          </motion.div>
        )}
      </div>
    </AppLayout>
  );
}
