'use client';
import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import dynamic from 'next/dynamic';
import AppLayout from '../AppLayout';
import { STATUS_CONFIG } from '../data/mockData';
import { Layers, Droplets, Wind, AlertTriangle, MapPin, RefreshCw } from 'lucide-react';
import { api } from '../../services/api';

// Dynamic import to avoid SSR issues with Leaflet
const MapComponent = dynamic(() => import('../components/CauveryMap'), { ssr: false, loading: () => <MapSkeleton /> });

function MapSkeleton() {
  return (
    <div style={{
      width: '100%', height: '100%', minHeight: 500,
      background: 'rgba(15,32,68,0.6)', borderRadius: 20,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      flexDirection: 'column', gap: 16,
    }}>
      <div className="ring-spinner" style={{ width: 56, height: 56 }}>
        <MapPin size={22} color="#22d3ee" />
      </div>
      <p style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.4)' }}>Loading Cauvery Basin map…</p>
    </div>
  );
}

function ErrorBanner({ onRetry }: { onRetry: () => void }) {
  return (
    <div style={{
      width: '100%', height: '100%', minHeight: 500,
      background: 'rgba(251,113,133,0.05)', border: '1px solid rgba(251,113,133,0.15)', borderRadius: 20,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      flexDirection: 'column', gap: 16, padding: 32, textAlign: 'center',
    }}>
      <AlertTriangle size={36} color="#fb7185" />
      <p style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.45)', maxWidth: 280 }}>Failed to load live basin map data.</p>
      <button className="btn btn-primary" onClick={onRetry} style={{ padding: '6px 16px', gap: 6, fontSize: '0.75rem' }}>
        <RefreshCw size={12} /> Retry
      </button>
    </div>
  );
}

const LAYERS = [
  { id: 'stations',  label: 'Stations',   icon: Radio },
  { id: 'reservoirs',label: 'Reservoirs', icon: Droplets },
  { id: 'alerts',    label: 'Alerts',     icon: AlertTriangle },
];

function Radio({ size, color }: { size: number; color: string }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14"/></svg>;
}

export default function MapPage() {
  const [activeLayers, setActiveLayers] = useState<string[]>(['stations', 'reservoirs', 'alerts']);
  const [selected, setSelected] = useState<string | null>(null);
  const [stations, setStations] = useState<any[]>([]);
  const [reservoirs, setReservoirs] = useState<any[]>([]);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [hasError, setHasError] = useState<boolean>(false);

  const fetchMapData = async () => {
    try {
      setIsLoading(true);
      setHasError(false);
      await api.login();
      const [dash, activeAlerts] = await Promise.all([
        api.getDashboard(),
        api.getAlerts()
      ]);
      setStations(dash.stations);
      setReservoirs(dash.reservoirs);
      setAlerts(activeAlerts);
    } catch (err) {
      console.error('Failed to load map data:', err);
      setHasError(true);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchMapData();
  }, []);

  const toggleLayer = (id: string) => {
    setActiveLayers(l => l.includes(id) ? l.filter(x => x !== id) : [...l, id]);
  };

  const selectedItem = selected ? (
    stations.find(st => st.id === selected) || reservoirs.find(r => r.id === selected)
  ) : null;

  // Group counts by risk status
  const statusCounts = (() => {
    let safe = 0, alert = 0, warning = 0, danger = 0;
    stations.forEach(s => {
      const r = (s.risk_level || 'Safe').toLowerCase();
      if (r === 'severe flood' || r === 'high risk') danger++;
      else if (r === 'moderate risk') warning++;
      else if (r === 'low risk') alert++;
      else safe++;
    });
    return { safe, alert, warning, danger };
  })();

  return (
    <AppLayout>
      <div style={{ padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 16, height: 'calc(100vh - 64px)', boxSizing: 'border-box' }}>

        {/* Layer controls */}
        <motion.div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}
          initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}
        >
          {LAYERS.map(l => (
            <motion.button
              key={l.id}
              className={activeLayers.includes(l.id) ? 'btn btn-primary' : 'btn btn-ghost'}
              onClick={() => toggleLayer(l.id)}
              whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }}
              style={{ fontSize: '0.78rem', padding: '6px 14px' }}
            >
              <l.icon size={12} color={activeLayers.includes(l.id) ? '#0a1628' : 'rgba(255,255,255,0.5)'} />
              {l.label}
            </motion.button>
          ))}
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="badge badge-safe"><span className="status-dot status-safe" />Safe: {statusCounts.safe}</span>
            <span className="badge badge-alert"><span className="status-dot status-alert" />Alert: {statusCounts.alert}</span>
            <span className="badge badge-warning"><span className="status-dot status-warning" />Warning: {statusCounts.warning}</span>
            <span className="badge badge-danger"><span className="status-dot status-danger" />Danger: {statusCounts.danger}</span>
          </div>
        </motion.div>

        {/* Map */}
        <motion.div style={{ flex: 1, borderRadius: 20, overflow: 'hidden', border: '1px solid rgba(255,255,255,0.08)', minHeight: 520, position: 'relative' }}
          initial={{ opacity: 0, scale: 0.99 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.2 }}
        >
          {isLoading ? (
            <MapSkeleton />
          ) : hasError ? (
            <ErrorBanner onRetry={fetchMapData} />
          ) : (
            <MapComponent
              activeLayers={activeLayers}
              onSelect={setSelected}
              stations={stations}
              reservoirs={reservoirs}
              alerts={alerts}
            />
          )}
        </motion.div>

        {/* Selected station info */}
        {selectedItem && (
          <motion.div
            className="glass-card" style={{ padding: 16 }}
            initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
          >
            {(() => {
              const s = selectedItem;
              const isReservoir = 'storage_pct' in s;
              
              if (isReservoir) {
                const pct = s.storage_pct;
                const severity = pct > 90 ? 'danger' : pct > 80 ? 'warning' : pct > 65 ? 'alert' : 'safe';
                const sc = STATUS_CONFIG[severity];
                return (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                    <MapPin size={16} color={sc.color} />
                    <div>
                      <strong style={{ color: '#e2e8f0' }}>{s.name}</strong>
                      <span style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.4)', marginLeft: 8 }}>Reservoir · Karnataka / Tamil Nadu</span>
                    </div>
                    <span className={`badge badge-${severity}`}>{s.status}</span>
                    <div style={{ marginLeft: 'auto', display: 'flex', gap: 24 }}>
                      <div><div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)' }}>Storage fill</div><strong style={{ color: sc.color, fontFamily: 'var(--font-mono)' }}>{s.storage_pct.toFixed(1)}%</strong></div>
                      <div><div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)' }}>Current storage</div><strong style={{ color: sc.color, fontFamily: 'var(--font-mono)' }}>{s.current_storage_mcft.toFixed(0)} MCFT</strong></div>
                      <div><div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)' }}>Spillway release</div><strong style={{ color: '#fb7185', fontFamily: 'var(--font-mono)' }}>{s.release_cumecs.toFixed(1)} m³/s</strong></div>
                    </div>
                    <button className="btn btn-ghost" onClick={() => setSelected(null)} style={{ fontSize: '0.75rem' }}>✕</button>
                  </div>
                );
              } else {
                const rawStatus = (s.risk_level || 'Safe').toLowerCase();
                const severity = rawStatus === 'severe flood' || rawStatus === 'high risk' ? 'danger' : rawStatus === 'moderate risk' ? 'warning' : rawStatus === 'low risk' ? 'alert' : 'safe';
                const sc = STATUS_CONFIG[severity];
                return (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                    <MapPin size={16} color={sc.color} />
                    <div>
                      <strong style={{ color: '#e2e8f0' }}>{s.name}</strong>
                      <span style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.4)', marginLeft: 8 }}>{s.basin} Basin • Elevation {s.elevation}m</span>
                    </div>
                    <span className={`badge badge-${severity}`}>{sc.label}</span>
                    <div style={{ marginLeft: 'auto', display: 'flex', gap: 24 }}>
                      <div><div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)' }}>Water Level</div><strong style={{ color: sc.color, fontFamily: 'var(--font-mono)' }}>{s.water_level.toFixed(2)}ft</strong></div>
                      <div><div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)' }}>Discharge</div><strong style={{ color: sc.color, fontFamily: 'var(--font-mono)' }}>{s.discharge.toFixed(1)} m³/s</strong></div>
                      <div><div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)' }}>Danger level</div><strong style={{ color: '#fb7185', fontFamily: 'var(--font-mono)' }}>{s.danger_level.toFixed(1)}ft</strong></div>
                    </div>
                    <button className="btn btn-ghost" onClick={() => setSelected(null)} style={{ fontSize: '0.75rem' }}>✕</button>
                  </div>
                );
              }
            })()}
          </motion.div>
        )}
      </div>
    </AppLayout>
  );
}
