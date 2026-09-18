'use client';
import { motion } from 'framer-motion';
import { useState, useEffect } from 'react';
import AppLayout from '../AppLayout';
import { FileText, Download, Share2, TrendingUp, Shield, Droplets, Brain, AlertTriangle, RefreshCw } from 'lucide-react';
import { api } from '../../services/api';
import { STATUS_CONFIG } from '../data/mockData';

import PageHeader from '../components/PageHeader';

const REPORT_DATE = new Date().toLocaleDateString('en-IN', { day: '2-digit', month: 'long', year: 'numeric' });

function ReportCard({ title, icon: Icon, color, children, delay }: { title: string; icon: any; color: string; children: React.ReactNode; delay: number }) {
  return (
    <motion.div
      className="glass-card"
      style={{ padding: 24, borderTop: `2px solid ${color}` }}
      initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <div style={{ width: 32, height: 32, borderRadius: 8, background: `${color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Icon size={16} color={color} />
        </div>
        <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#e2e8f0' }}>{title}</h3>
      </div>
      {children}
    </motion.div>
  );
}

export default function ReportsPage() {
  const [dashboardData, setDashboardData] = useState<any>(null);
  const [diagnostics, setDiagnostics] = useState<any>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [hasError, setHasError] = useState<boolean>(false);

  const fetchReportsData = async () => {
    try {
      setIsLoading(true);
      setHasError(false);
      await api.login();
      const [dash, diag] = await Promise.all([
        api.getDashboard(),
        api.getDiagnostics()
      ]);
      setDashboardData(dash);
      setDiagnostics(diag);
    } catch (err) {
      console.error('Failed to load reports summary:', err);
      setHasError(true);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchReportsData();
  }, []);

  if (isLoading) {
    return (
      <AppLayout>
        <div style={{ padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div style={{ height: 140, background: 'rgba(255,255,255,0.03)', borderRadius: 20 }} className="shimmer" />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            {[1, 2, 3, 4].map(i => (
              <div key={i} style={{ height: 180, background: 'rgba(255,255,255,0.03)', borderRadius: 16 }} className="shimmer" />
            ))}
          </div>
        </div>
      </AppLayout>
    );
  }

  if (hasError || !dashboardData) {
    return (
      <AppLayout>
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          minHeight: 'calc(100vh - 120px)', gap: 16, padding: 32, textAlign: 'center',
        }}>
          <AlertTriangle size={48} color="#fb7185" />
          <h3 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#e2e8f0' }}>Reports Offline</h3>
          <button className="btn btn-primary" onClick={fetchReportsData}>
            <RefreshCw size={14} /> Retry
          </button>
        </div>
      </AppLayout>
    );
  }

  const stations = dashboardData.stations || [];
  const reservoirs = dashboardData.reservoirs || [];

  return (
    <AppLayout>
      <div style={{ padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 20 }}>

        {/* Standardized Government Page Header */}
        <PageHeader
          title="Model Evaluation & System Reports"
          subtitle="Verified performance results and system evaluation"
          purpose="Review held-out model performance and generated evaluation reports."
          badges={[
            { label: 'Evaluation: Offline Held-Out Test', variant: 'info' },
            { label: 'Test NSE: 0.9968', variant: 'safe' },
            { label: 'Test RMSE: 0.4974 m', variant: 'info' },
            { label: 'Test MAE: 0.1786 m', variant: 'safe' },
          ]}
        />

        {/* Report metadata card */}
        <motion.div className="glass-card gradient-border" style={{ padding: 24 }}
          initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 12, flexWrap: 'wrap', gap: 16 }}>
            <div>
              <div style={{ fontSize: '0.7rem', color: '#22d3ee', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 6, fontWeight: 800 }}>OFFICIAL EVALUATION DOSSIER</div>
              <h2 style={{ fontSize: '1.3rem', fontWeight: 800, color: '#f8fafc', marginBottom: 6 }}>
                HydroGNN-Net System Status & Model Benchmark
              </h2>
              <p style={{ fontSize: '0.82rem', color: 'rgba(255,255,255,0.6)', maxWidth: 620, lineHeight: 1.6, margin: 0 }}>
                Official verification report for the Cauvery River Basin flood-monitoring network and Experiment 9 Spatio-Temporal Graph Neural Network.
              </p>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end' }}>
              <div style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.45)' }}>Generated: {REPORT_DATE}</div>
              <div style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.45)' }}>Architecture: Experiment 9 (ST-GNN)</div>
              <div style={{ fontSize: '0.78rem', color: '#34d399', fontWeight: 600 }}>Status: Verified & Production Deployed</div>
              <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                <motion.button className="btn btn-primary" style={{ fontSize: '0.78rem', padding: '6px 14px' }} whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }}>
                  <Download size={13} />Export PDF
                </motion.button>
                <motion.button className="btn btn-ghost" style={{ fontSize: '0.78rem', padding: '6px 12px' }} whileHover={{ scale: 1.04 }}>
                  <Share2 size={13} />Share
                </motion.button>
              </div>
            </div>
          </div>
        </motion.div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>

          {/* Model Performance - Verified Offline Metrics */}
          <ReportCard title="Experiment 9 Held-Out Benchmark Performance" icon={Brain} color="#22d3ee" delay={0.1}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              {[
                ['Evaluation Type', 'Offline Held-Out Test', '#a78bfa'],
                ['Test NSE',        '0.9968',               '#22d3ee'],
                ['Test RMSE',       '0.4974 m',             '#38bdf8'],
                ['Test MAE',        '0.1786 m',             '#34d399'],
                ['Native Horizons', '6h, 12h, 24h',         '#f8fafc'],
                ['Interpolation',   'PCHIP Spline (1h/3h/18h)', '#94a3b8'],
                ['Edge Conv',       'GATv2 + GraphSAGE',    '#cbd5e1'],
                ['Residual Gate',   'Trend-Conditioned',    '#34d399'],
              ].map(([k, v, c]) => (
                <div key={k} style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 8, padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.45)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{k}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem', fontWeight: 700, color: c as string }}>{v}</span>
                </div>
              ))}
            </div>
            <div style={{ marginTop: 12, padding: '8px 12px', background: 'rgba(34,211,238,0.06)', borderRadius: 6, border: '1px solid rgba(34,211,238,0.15)', fontSize: '0.74rem', color: 'rgba(255,255,255,0.65)' }}>
              Note: NSE is the Nash-Sutcliffe Efficiency metric measuring hydrological variance explained relative to observed gauge discharge. It is not classification accuracy.
            </div>
          </ReportCard>

          {/* Station Summary */}
          <ReportCard title="Station Monitoring Summary" icon={TrendingUp} color="#a78bfa" delay={0.2}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 190, overflowY: 'auto', paddingRight: 4 }}>
              {stations.map((s: any) => {
                const pct = (s.water_level / s.danger_level) * 100;
                const rSev = (s.risk_level || 'Safe').toLowerCase();
                const severity = rSev === 'severe flood' || rSev === 'high risk' ? 'danger' : rSev === 'moderate risk' ? 'warning' : rSev === 'low risk' ? 'alert' : 'safe';
                const c = STATUS_CONFIG[severity]?.color || '#34d399';
                return (
                  <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span className={`status-dot status-${severity}`} style={{ flexShrink: 0 }} />
                    <span style={{ fontSize: '0.78rem', width: 120, flexShrink: 0, color: 'rgba(255,255,255,0.7)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {s.name.replace(' Gauge', '').replace(' Reservoir', '')}
                    </span>
                    <div style={{ flex: 1, height: 4, background: 'rgba(255,255,255,0.08)', borderRadius: 2, overflow: 'hidden' }}>
                      <motion.div style={{ height: '100%', background: c, borderRadius: 2, width: 0 }}
                        animate={{ width: `${pct}%` }} transition={{ delay: 0.5, duration: 1 }} />
                    </div>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: c, width: 50, textAlign: 'right' }}>{s.water_level.toFixed(1)}ft</span>
                  </div>
                );
              })}
            </div>
          </ReportCard>

          {/* Reservoir Status */}
          <ReportCard title="Reservoir Storage Report" icon={Droplets} color="#06b6d4" delay={0.3}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 190, overflowY: 'auto', paddingRight: 4 }}>
              {reservoirs.map((r: any) => {
                const pct = r.storage_pct;
                const color = pct > 90 ? '#fb7185' : pct > 75 ? '#fb923c' : '#22d3ee';
                return (
                  <div key={r.id} style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 8, padding: '8px 12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                      <span style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.7)' }}>{r.name}</span>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: color, fontWeight: 700 }}>{pct.toFixed(1)}%</span>
                    </div>
                    <div style={{ height: 3, background: 'rgba(255,255,255,0.07)', borderRadius: 2, overflow: 'hidden' }}>
                      <motion.div style={{ height: '100%', background: color, width: 0 }}
                        animate={{ width: `${pct}%` }} transition={{ delay: 0.6, duration: 1.2 }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </ReportCard>

          {/* System status */}
          <ReportCard title="System Health" icon={Shield} color="#34d399" delay={0.4}>
            {[
              { label: 'Model Inference',     status: 'ONLINE',   color: '#34d399' },
              { label: 'Database Health',     status: diagnostics?.database_health === 'Healthy' ? 'ONLINE' : 'ERROR', color: diagnostics?.database_health === 'Healthy' ? '#34d399' : '#fb7185' },
              { label: 'Scheduler Health',    status: diagnostics?.scheduler_status === 'Healthy' ? 'ONLINE' : 'ERROR', color: diagnostics?.scheduler_status === 'Healthy' ? '#34d399' : '#fb7185' },
              { label: 'Active warnings count', status: `${stations.filter((s: any) => s.risk_level === 'High Risk' || s.risk_level === 'Severe Flood').length} active`, color: '#fb7185' },
              { label: 'Telemetry Drift status', status: diagnostics?.data_drift || 'Stable', color: '#34d399' },
              { label: 'Model Tag deployed', status: diagnostics?.model_drift.split('|')[0]?.trim() || 'HydroGNN v1.1.0', color: '#22d3ee' },
            ].map(s => (
              <div key={s.label} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                <span style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.55)' }}>{s.label}</span>
                <span style={{ fontSize: '0.72rem', fontWeight: 700, color: s.color, fontFamily: 'var(--font-mono)' }}>{s.status}</span>
              </div>
            ))}
          </ReportCard>
        </div>
      </div>
    </AppLayout>
  );
}
