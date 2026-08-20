'use client';
import { motion } from 'framer-motion';
import { useState, useEffect, useMemo } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import AppLayout from '../AppLayout';
import { STATUS_CONFIG } from '../data/mockData';
import { MapPin, AlertTriangle, RefreshCw } from 'lucide-react';
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
      setStations(dash.stations);

      const hasMettur = dash.stations.some(s => s.id === 'METTUR');
      const firstStation = dash.stations[0]?.id || 'METTUR';
      const initialStation = hasMettur ? 'METTUR' : firstStation;
      setSelectedStationId(initialStation);

      const pred = await api.getPrediction(initialStation);
      setPredictionData(pred);
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
    return predictionData.hydrograph.map((h: any) => ({
      time: h.time,
      level: h.observed,
      forecast: h.predicted
    }));
  }, [predictionData]);

  if (isLoading) {
    return (
      <AppLayout>
        <div style={{ padding: '24px 32px', display: 'flex', gap: 20, height: 'calc(100vh - 64px)' }}>
          <div style={{ width: 280, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[1, 2, 3, 4, 5].map(i => (
              <div key={i} style={{ height: 75, background: 'rgba(255,255,255,0.03)', borderRadius: 12 }} className="shimmer" />
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

  return (
    <AppLayout>
      <div style={{ padding: '24px 32px', display: 'flex', gap: 20, height: 'calc(100vh - 64px)', overflowY: 'auto', boxSizing: 'border-box' }}>

        {/* Station list */}
        <div style={{ width: 280, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 8, maxHeight: '100%', overflowY: 'auto', paddingRight: 4 }}>
          <p style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'rgba(255,255,255,0.3)', marginBottom: 4 }}>SELECT STATION ({stations.length})</p>
          {stations.map((s, i) => {
            const rSev = (s.risk_level || 'Safe').toLowerCase();
            const sSev = rSev === 'severe flood' || rSev === 'high risk' ? 'danger' : rSev === 'moderate risk' ? 'warning' : rSev === 'low risk' ? 'alert' : 'safe';
            const c = STATUS_CONFIG[sSev] || STATUS_CONFIG.safe;
            const isActive = s.id === selectedStationId;
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
                  border: `1px solid ${isActive ? c.border : 'rgba(255,255,255,0.06)'}`,
                  background: isActive ? c.bg : 'rgba(255,255,255,0.02)',
                  boxShadow: isActive ? c.shadow : 'none',
                  transition: 'all 0.2s',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <span className={`status-dot status-${sSev}`} />
                  <span style={{ fontWeight: 600, fontSize: '0.82rem', color: '#e2e8f0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 120 }}>{s.name.replace(' Gauge', '').replace(' Reservoir', '')}</span>
                  <span className={`badge badge-${sSev}`} style={{ marginLeft: 'auto', fontSize: '0.6rem', padding: '1px 5px' }}>{c.label}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.9rem', fontWeight: 700, color: c.color }}>{s.water_level?.toFixed(1)}ft</span>
                  <span style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)' }}>Risk: {s.flood_probability || 0}%</span>
                </div>
              </motion.div>
            );
          })}
        </div>

        {/* Station detail */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <motion.div className="glass-card" style={{ padding: 24 }}
            key={selected.id}
            initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <MapPin size={18} color={sc.color} />
                  <h2 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#e2e8f0' }}>{selected.name}</h2>
                  <span className={`badge badge-${severity}`}>
                    <span className={`status-dot status-${severity}`} />
                    {sc.label}
                  </span>
                </div>
                <p style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.4)', marginTop: 4 }}>
                  {selected.basin} Basin · Elevation {selected.elevation}m
                </p>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '2rem', fontWeight: 800, color: sc.color }}>{selected.water_level?.toFixed(2)}ft</div>
                <div style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.4)' }}>of {selected.danger_level?.toFixed(1)}ft max threshold</div>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12, marginBottom: 20 }}>
              {[
                { label: 'Flood Risk', value: `${selected.flood_probability || 0}%`, color: (selected.flood_probability || 0) > 60 ? '#fb7185' : (selected.flood_probability || 0) > 30 ? '#fb923c' : '#34d399' },
                { label: 'NSE Accuracy', value: '0.880', color: '#22d3ee' },
                { label: 'Discharge Flow', value: `${selected.discharge.toFixed(1)} m³/s`, color: '#e2e8f0' },
                { label: 'Warning level', value: selected.warning_level != null ? `${selected.warning_level.toFixed(1)}ft` : 'N/A', color: sc.color },
              ].map(m => (
                <div key={m.label} style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 10, padding: '12px 14px' }}>
                  <div style={{ fontSize: '0.68rem', color: 'rgba(255,255,255,0.35)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>{m.label}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1rem', fontWeight: 700, color: m.color }}>{m.value}</div>
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', gap: 32 }}>
              <div>
                <span style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.35)' }}>Observed Rain</span>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1rem', color: '#a78bfa', fontWeight: 700, marginTop: 4 }}>{selected.rain_observed.toFixed(1)} mm</div>
              </div>
              <div>
                <span style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.35)' }}>Soil Moisture</span>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1rem', color: '#34d399', fontWeight: 700, marginTop: 4 }}>{(selected.soil_moisture * 100).toFixed(0)}%</div>
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.35)' }}>Danger Level Ratio</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: sc.color }}>{pct.toFixed(0)}%</span>
                </div>
                <div className="progress-track">
                  <motion.div className="progress-fill" style={{ background: sc.color, width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 1 }} />
                </div>
              </div>
            </div>
          </motion.div>

          {/* Hydrograph card */}
          <motion.div className="glass-card gradient-border" style={{ padding: '22px 24px', flex: 1, minHeight: 300 }}
            initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <div>
                <div style={{ fontSize: '0.95rem', fontWeight: 700 }}>AI Forecaster Hydrograph</div>
                <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.35)', marginTop: 2 }}>Observed water level convolved with GNN 24h prediction interval</div>
              </div>
            </div>

            <ResponsiveContainer width="100%" height={260}>
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
                  label={{ value: 'Danger Threshold', position: 'right', fontSize: 9, fill: '#fb7185' }} />
                <Area type="monotone" dataKey="level" stroke="#22d3ee" strokeWidth={2} fill="url(#actualGrad)" name="Observed (ft)" dot={false} />
                <Area type="monotone" dataKey="forecast" stroke="#a78bfa" strokeWidth={1.8} fill="url(#forecastGrad)" name="AI Forecast (ft)" strokeDasharray="5 3" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </motion.div>
        </div>
      </div>
    </AppLayout>
  );
}
