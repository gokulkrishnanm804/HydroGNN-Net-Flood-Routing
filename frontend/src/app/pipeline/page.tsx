'use client';
import { motion } from 'framer-motion';
import { useState, useEffect } from 'react';
import AppLayout from '../AppLayout';
import { CheckCircle, XCircle, Clock, Database, AlertTriangle, Cpu, HardDrive, ShieldCheck, RefreshCw } from 'lucide-react';
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
  const apiHealth = diagnostics.status === 'Healthy' ? 'healthy' : 'warning';
  const schedHealth = diagnostics.scheduler_status === 'Healthy' ? 'healthy' : 'warning';

  return (
    <AppLayout>
      <div style={{ padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 20 }}>

        {/* Overall progress */}
        <motion.div className="glass-card gradient-border" style={{ padding: 28 }}
          initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 20, marginBottom: 20 }}>
            <div className="ring-spinner" style={{ width: 56, height: 56 }}>
              <Database size={22} color="#22d3ee" />
            </div>
            <div>
              <h2 style={{ fontSize: '1.2rem', fontWeight: 800 }}>System diagnostics</h2>
              <p style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.4)', marginTop: 2 }}>
                HydroGNN-Net telemetry nodes latency and database connectivity metrics
              </p>
            </div>
            <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '2rem', fontWeight: 800, color: '#22d3ee' }}>
                {diagnostics.api_latency_ms.toFixed(1)} ms
              </div>
              <div style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.4)' }}>API query latency</div>
            </div>
          </div>
        </motion.div>

        {/* Dataset / Service cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 14 }}>
          
          {/* DB Health */}
          <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
            className="glass-card" style={{ padding: 20, borderColor: `${STATUS_META[dbHealth].color}25` }}
            whileHover={{ y: -3, borderColor: `${STATUS_META[dbHealth].color}50` }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <div style={{ width: 36, height: 36, borderRadius: 9, background: `${STATUS_META[dbHealth].color}15`, border: `1px solid ${STATUS_META[dbHealth].color}30`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Database size={16} color={STATUS_META[dbHealth].color} />
              </div>
              <div>
                <div style={{ fontSize: '0.88rem', fontWeight: 600, color: '#e2e8f0' }}>SQLite Database Connection</div>
                <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.35)' }}>Capacity: {diagnostics.prediction_count} records</div>
              </div>
            </div>
            <div style={{ fontSize: '0.8rem', color: STATUS_META[dbHealth].color, fontWeight: 700 }}>
              {STATUS_META[dbHealth].label}
            </div>
          </motion.div>

          {/* Background Ingestion Scheduler */}
          <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
            className="glass-card" style={{ padding: 20, borderColor: `${STATUS_META[schedHealth].color}25` }}
            whileHover={{ y: -3, borderColor: `${STATUS_META[schedHealth].color}50` }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <div style={{ width: 36, height: 36, borderRadius: 9, background: `${STATUS_META[schedHealth].color}15`, border: `1px solid ${STATUS_META[schedHealth].color}30`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <ShieldCheck size={16} color={STATUS_META[schedHealth].color} />
              </div>
              <div>
                <div style={{ fontSize: '0.88rem', fontWeight: 600, color: '#e2e8f0' }}>Ingestion Sync Scheduler</div>
                <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.35)' }}>Last tick: {diagnostics.last_updated.split('T')[1]?.split('.')[0] || 'Nominal'}</div>
              </div>
            </div>
            <div style={{ fontSize: '0.8rem', color: STATUS_META[schedHealth].color, fontWeight: 700 }}>
              {STATUS_META[schedHealth].label}
            </div>
          </motion.div>

          {/* Model Health */}
          <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
            className="glass-card" style={{ padding: 20, borderColor: 'rgba(34,211,238,0.25)' }}
            whileHover={{ y: -3, borderColor: 'rgba(34,211,238,0.5)' }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <div style={{ width: 36, height: 36, borderRadius: 9, background: 'rgba(34,211,238,0.15)', border: '1px solid rgba(34,211,238,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Clock size={16} color="#22d3ee" />
              </div>
              <div>
                <div style={{ fontSize: '0.88rem', fontWeight: 600, color: '#e2e8f0' }}>AI GNN Inference Latency</div>
                <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.35)' }}>Average model run time</div>
              </div>
            </div>
            <div style={{ fontSize: '0.8rem', color: '#22d3ee', fontWeight: 700 }}>
              {diagnostics.inference_latency_avg_ms.toFixed(1)} ms
            </div>
          </motion.div>

        </div>

        {/* Resources / Drift Info */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          
          {/* Server Resources */}
          <motion.div className="glass-card" style={{ padding: 24 }}
            initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}
          >
            <h3 style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: 16 }}>Server Host Resources</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.6)', display: 'flex', alignItems: 'center', gap: 6 }}><Cpu size={14} /> CPU Utilization</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: '#34d399', fontWeight: 600 }}>{diagnostics.system_metrics.cpu_usage_pct.toFixed(0)}%</span>
                </div>
                <div className="progress-track" style={{ height: 6 }}>
                  <motion.div className="progress-fill" style={{ width: `${diagnostics.system_metrics.cpu_usage_pct}%`, background: '#34d399' }} />
                </div>
              </div>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.6)', display: 'flex', alignItems: 'center', gap: 6 }}><HardDrive size={14} /> Memory Allocation</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: '#22d3ee', fontWeight: 600 }}>{diagnostics.system_metrics.memory_usage_pct.toFixed(0)}%</span>
                </div>
                <div className="progress-track" style={{ height: 6 }}>
                  <motion.div className="progress-fill" style={{ width: `${diagnostics.system_metrics.memory_usage_pct}%`, background: '#22d3ee' }} />
                </div>
              </div>
            </div>
          </motion.div>

          {/* Model & Data Quality Drift */}
          <motion.div className="glass-card" style={{ padding: 24 }}
            initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }}
          >
            <h3 style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: 16 }}>Data Drift & Model Status</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ padding: '8px 12px', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 8 }}>
                <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.35)' }}>Active model tag</div>
                <div style={{ fontSize: '0.82rem', color: '#e2e8f0', fontWeight: 600, marginTop: 2 }}>{diagnostics.model_drift.split('|')[0] || 'HydroGNN v1'}</div>
              </div>
              <div style={{ padding: '8px 12px', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 8 }}>
                <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.35)' }}>Validation metrics</div>
                <div style={{ fontSize: '0.82rem', color: '#22d3ee', fontWeight: 600, marginTop: 2 }}>{diagnostics.model_drift.split('|')[1] || 'Val NSE=0.880 | Val RMSE=0.090 m'}</div>
              </div>
              <div style={{ padding: '8px 12px', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 8 }}>
                <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.35)' }}>Telemetry data drift quality</div>
                <div style={{ fontSize: '0.82rem', color: '#34d399', fontWeight: 600, marginTop: 2 }}>{diagnostics.data_drift}</div>
              </div>
            </div>
          </motion.div>

        </div>
      </div>
    </AppLayout>
  );
}
