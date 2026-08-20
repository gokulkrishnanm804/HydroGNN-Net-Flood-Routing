'use client';
import { motion, AnimatePresence } from 'framer-motion';
import { useState, useEffect, useMemo } from 'react';
import AppLayout from '../AppLayout';
import { STATUS_CONFIG } from '../data/mockData';
import { AlertTriangle, Bell, BellOff, Clock, MapPin, TrendingUp, X, RefreshCw } from 'lucide-react';
import { api } from '../../services/api';

const TYPE_COLORS: Record<string, string> = {
  LEVEL_CRITICAL: '#fb7185',
  RISING_TREND:   '#fb923c',
  RESERVOIR_HIGH: '#fbbf24',
  FORECAST_WARN:  '#fb923c',
  INFLOW_SPIKE:   '#fbbf24',
  RESOLVED:       '#34d399',
  CRITICAL:       '#fb7185',
  WARNING:        '#fb923c',
  ALERT:          '#fbbf24',
};

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<any[]>([]);
  const [filter, setFilter] = useState<'all' | 'active'>('active');
  const [dismissed, setDismissed] = useState<number[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [hasError, setHasError] = useState<boolean>(false);

  const fetchAlerts = async () => {
    try {
      setIsLoading(true);
      setHasError(false);
      await api.login();
      const logs = await api.getAlerts();
      
      // Inject numerical IDs for React map rendering keys
      const formatted = logs.map((l: any, i: number) => ({
        ...l,
        id: l.id || (i + 1),
        // Standardize keys
        severity: l.severity || 'WARNING',
        station: l.station_name || 'System',
        time: l.timestamp.split(' ')[1] || 'Just now',
        type: l.event_type || 'ALERT',
        msg: l.message,
        active: l.active !== undefined ? l.active : true,
      }));
      setAlerts(formatted);
    } catch (err) {
      console.error('Failed to load alert logs:', err);
      setHasError(true);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchAlerts();
  }, []);

  const shown = useMemo(() => {
    return alerts
      .filter(a => !dismissed.includes(a.id))
      .filter(a => filter === 'all' || a.active);
  }, [alerts, dismissed, filter]);

  // Alert summary counts
  const summary = useMemo(() => {
    const activeAlerts = alerts.filter(a => a.active && !dismissed.includes(a.id));
    const warnings = activeAlerts.filter(a => a.severity.toLowerCase() === 'warning');
    const critical = activeAlerts.filter(a => a.severity.toLowerCase() === 'critical');
    return {
      active: activeAlerts.length,
      warnings: warnings.length,
      critical: critical.length,
      resolved: alerts.filter(a => !a.active).length,
    };
  }, [alerts, dismissed]);

  if (isLoading) {
    return (
      <AppLayout>
        <div style={{ padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
            {[1, 2, 3, 4].map(i => (
              <div key={i} style={{ height: 90, background: 'rgba(255,255,255,0.03)', borderRadius: 14 }} className="shimmer" />
            ))}
          </div>
          <div style={{ height: 110, background: 'rgba(255,255,255,0.03)', borderRadius: 16 }} className="shimmer" />
          <div style={{ height: 110, background: 'rgba(255,255,255,0.03)', borderRadius: 16 }} className="shimmer" />
        </div>
      </AppLayout>
    );
  }

  if (hasError) {
    return (
      <AppLayout>
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          minHeight: 'calc(100vh - 120px)', gap: 16, padding: 32, textAlign: 'center',
        }}>
          <AlertTriangle size={48} color="#fb7185" />
          <h3 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#e2e8f0' }}>Failed to Load Alerts</h3>
          <button className="btn btn-primary" onClick={fetchAlerts}>
            <RefreshCw size={14} /> Retry
          </button>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div style={{ padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 20 }}>

        {/* Summary row */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          {[
            { label: 'Active Alerts',  value: summary.active,  color: '#fb7185', bg: 'rgba(244,63,94,0.1)' },
            { label: 'Warnings',       value: summary.warnings, color: '#fb923c', bg: 'rgba(251,146,60,0.1)' },
            { label: 'Critical Risks',  value: summary.critical, color: '#fbbf24', bg: 'rgba(251,191,36,0.1)' },
            { label: 'Resolved (24h)', value: summary.resolved, color: '#34d399', bg: 'rgba(52,211,153,0.1)' },
          ].map((s, i) => (
            <motion.div key={s.label}
              initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.08 }}
              style={{ background: s.bg, border: `1px solid ${s.color}25`, borderRadius: 14, padding: '16px 18px' }}
            >
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '2rem', fontWeight: 800, color: s.color }}>{s.value}</div>
              <div style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.5)', textTransform: 'uppercase', letterSpacing: '0.07em', marginTop: 4 }}>{s.label}</div>
            </motion.div>
          ))}
        </div>

        {/* Filter */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {(['active', 'all'] as const).map(f => (
            <button key={f} className={filter === f ? 'btn btn-primary' : 'btn btn-ghost'}
              onClick={() => setFilter(f)} style={{ fontSize: '0.8rem', padding: '6px 16px' }}>
              {f === 'active' ? <Bell size={13} /> : <BellOff size={13} />}
              {f === 'active' ? 'Active Only' : 'All Alerts'}
            </button>
          ))}
          <span style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'rgba(255,255,255,0.4)' }}>
            {shown.length} alert{shown.length !== 1 ? 's' : ''} shown
          </span>
        </div>

        {/* Alert list */}
        <AnimatePresence>
          {shown.map((a, i) => {
            const rawSev = a.severity.toLowerCase();
            const severity = rawSev === 'critical' ? 'danger' : rawSev === 'warning' ? 'warning' : rawSev === 'alert' ? 'alert' : 'safe';
            const sc = STATUS_CONFIG[severity] || STATUS_CONFIG.safe;
            const typeColor = TYPE_COLORS[a.type] || '#fb7185';
            
            return (
              <motion.div key={a.id}
                initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, x: 40, height: 0 }}
                transition={{ delay: i * 0.06 }}
                style={{
                  background: `${sc.bg}`,
                  border: `1px solid ${sc.border}`,
                  borderRadius: 16,
                  padding: '18px 20px',
                  boxShadow: a.active ? sc.shadow : 'none',
                  position: 'relative',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
                  <div style={{ width: 40, height: 40, borderRadius: 10, background: `${typeColor}20`, border: `1px solid ${typeColor}40`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    <AlertTriangle size={18} color={typeColor} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6, flexWrap: 'wrap' }}>
                      <span style={{ fontWeight: 700, fontSize: '0.9rem', color: '#e2e8f0' }}>{a.station}</span>
                      <span className={`badge badge-${severity}`} style={{ fontSize: '0.62rem' }}>
                        <span className={`status-dot status-${severity}`} />
                        {sc.label}
                      </span>
                      <span style={{ fontSize: '0.7rem', color: typeColor, background: `${typeColor}15`, padding: '2px 8px', borderRadius: 4, fontWeight: 600, letterSpacing: '0.04em' }}>{a.type.replace(/_/g, ' ')}</span>
                      {a.active && <span style={{ fontSize: '0.65rem', color: '#34d399', background: 'rgba(52,211,153,0.1)', padding: '2px 8px', borderRadius: 4 }}>ACTIVE</span>}
                    </div>
                    <p style={{ fontSize: '0.82rem', color: 'rgba(255,255,255,0.7)', lineHeight: 1.5, margin: 0 }}>{a.msg}</p>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 10 }}>
                      <Clock size={12} color="rgba(255,255,255,0.3)" />
                      <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.35)' }}>{a.time} (Database dispatch)</span>
                      <MapPin size={12} color="rgba(255,255,255,0.3)" />
                      <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.35)' }}>Cauvery Basin</span>
                    </div>
                  </div>
                  <motion.button
                    onClick={() => setDismissed(d => [...d, a.id])}
                    whileHover={{ scale: 1.1, color: '#fb7185' }}
                    whileTap={{ scale: 0.9 }}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.3)', padding: 4 }}
                  >
                    <X size={16} />
                  </motion.button>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>

        {shown.length === 0 && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            style={{ textAlign: 'center', padding: '60px 0', color: 'rgba(255,255,255,0.3)' }}
          >
            <Bell size={40} style={{ margin: '0 auto 12px', opacity: 0.3 }} />
            <p>No active alerts to display</p>
          </motion.div>
        )}
      </div>
    </AppLayout>
  );
}
