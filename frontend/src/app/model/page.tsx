'use client';
import { motion } from 'framer-motion';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, Radar } from 'recharts';
import AppLayout from '../AppLayout';
import { MODEL_METRICS, STATIONS } from '../data/mockData';
import { Brain, Zap, BarChart2, Cpu, Shield, Activity } from 'lucide-react';

const trainingData = Array.from({ length: MODEL_METRICS.training_epochs }, (_, i) => ({
  epoch: i + 1,
  train_loss: Math.max(0.05, 2.5 * Math.exp(-i * 0.04) + Math.sin(i * 0.3) * 0.05),
  val_loss:   Math.max(0.08, 2.8 * Math.exp(-i * 0.038) + Math.sin(i * 0.4) * 0.06),
  nse:        Math.min(0.95, 0.1 + (1 - Math.exp(-i * 0.035)) * 0.85),
})).filter((_, i) => i % 3 === 0);

const radarData = [
  { metric: 'NSE',      A: 89.1, fullMark: 100 },
  { metric: 'KGE',      A: 87.3, fullMark: 100 },
  { metric: 'POD',      A: 84.0, fullMark: 100 },
  { metric: 'CSI',      A: 78.0, fullMark: 100 },
  { metric: 'Accuracy', A: 88.0, fullMark: 100 },
  { metric: '1-FAR',    A: 88.0, fullMark: 100 },
];

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: 'rgba(10,22,40,0.95)', backdropFilter: 'blur(16px)', border: '1px solid rgba(34,211,238,0.2)', borderRadius: 10, padding: '8px 12px', fontSize: '0.78rem' }}>
      <p style={{ color: 'rgba(255,255,255,0.5)', marginBottom: 3 }}>Epoch {label}</p>
      {payload.map((p: any) => <p key={p.dataKey} style={{ color: p.color }}>{p.name}: <strong>{Number(p.value).toFixed(4)}</strong></p>)}
    </div>
  );
};

function ArchDiagram() {
  const layers = [
    { name: 'Input', desc: '13 features × 8 stations', color: '#22d3ee', icon: '→' },
    { name: 'GRU Encoder', desc: '2 layers, hidden=128', color: '#06b6d4', icon: '⟳' },
    { name: 'GATv2 Layer', desc: '4 heads, 2 layers', color: '#8b5cf6', icon: '⊗' },
    { name: 'GraphSAGE', desc: 'Neighbor aggregation', color: '#a78bfa', icon: '◎' },
    { name: 'Multi-Head Output', desc: '6 horizons: 1,3,6,12,18,24h', color: '#34d399', icon: '↗' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {layers.map((l, i) => (
        <motion.div key={l.name}
          initial={{ opacity: 0, x: -16 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.4 + i * 0.1 }}
          style={{
            display: 'flex', alignItems: 'center', gap: 12,
            padding: '12px 16px',
            borderRadius: 10,
            background: `${l.color}10`,
            border: `1px solid ${l.color}25`,
          }}
        >
          <div style={{ width: 32, height: 32, borderRadius: 8, background: `${l.color}20`, border: `1px solid ${l.color}40`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1rem', color: l.color, flexShrink: 0 }}>
            {l.icon}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#e2e8f0' }}>{l.name}</div>
            <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)' }}>{l.desc}</div>
          </div>
          {i < layers.length - 1 && (
            <div style={{ fontSize: '0.8rem', color: `${l.color}60` }}>↓</div>
          )}
        </motion.div>
      ))}
    </div>
  );
}

export default function ModelPage() {
  return (
    <AppLayout>
      <div style={{ padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 20 }}>

        {/* Status header */}
        <motion.div className="glass-card gradient-border" style={{ padding: 24 }}
          initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
            <div className="ring-spinner" style={{ width: 60, height: 60 }}>
              <Brain size={24} color="#22d3ee" />
            </div>
            <div>
              <h2 style={{ fontSize: '1.3rem', fontWeight: 800, color: '#e2e8f0', marginBottom: 4 }}>HydroGNN-Net v2.4</h2>
              <p style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.45)' }}>
                Spatio-Temporal Graph Neural Network · Trained on 6-year Cauvery Basin data
              </p>
            </div>
            <span className="badge badge-safe" style={{ marginLeft: 'auto', fontSize: '0.8rem', padding: '6px 14px' }}>
              <span className="status-dot status-safe" />LIVE INFERENCE
            </span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, marginTop: 20 }}>
            {[
              { label: 'Parameters', value: '2.85M', icon: Cpu, color: '#22d3ee' },
              { label: 'Best Epoch', value: `#${MODEL_METRICS.best_epoch}`, icon: Zap, color: '#a78bfa' },
              { label: 'NSE', value: MODEL_METRICS.nse.toFixed(3), icon: BarChart2, color: '#34d399' },
              { label: 'KGE', value: MODEL_METRICS.kge.toFixed(3), icon: Activity, color: '#06b6d4' },
              { label: 'Accuracy', value: `${(MODEL_METRICS.accuracy*100).toFixed(1)}%`, icon: Shield, color: '#fbbf24' },
            ].map(m => (
              <div key={m.label} style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 12, padding: 14, display: 'flex', flexDirection: 'column', gap: 6 }}>
                <m.icon size={16} color={m.color} />
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.2rem', fontWeight: 700, color: m.color }}>{m.value}</div>
                <div style={{ fontSize: '0.68rem', color: 'rgba(255,255,255,0.35)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{m.label}</div>
              </div>
            ))}
          </div>
        </motion.div>

        {/* Training curves + architecture */}
        <div className="grid-2">
          <motion.div className="glass-card" style={{ padding: 24 }}
            initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
          >
            <h3 style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: 4 }}>Training Curves</h3>
            <p style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.35)', marginBottom: 16 }}>Loss convergence over {MODEL_METRICS.training_epochs} epochs</p>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={trainingData} margin={{ top: 5, right: 10, left: -15, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="epoch" tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.3)' }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.3)' }} tickLine={false} axisLine={false} />
                <Tooltip content={<CustomTooltip />} />
                <Line type="monotone" dataKey="train_loss" stroke="#22d3ee" strokeWidth={2} dot={false} name="Train Loss" />
                <Line type="monotone" dataKey="val_loss"   stroke="#a78bfa" strokeWidth={2} dot={false} name="Val Loss" />
              </LineChart>
            </ResponsiveContainer>
          </motion.div>

          <motion.div className="glass-card" style={{ padding: 24 }}
            initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
          >
            <h3 style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: 4 }}>Performance Radar</h3>
            <p style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.35)', marginBottom: 12 }}>Multi-metric evaluation</p>
            <ResponsiveContainer width="100%" height={220}>
              <RadarChart data={radarData}>
                <PolarGrid stroke="rgba(255,255,255,0.1)" />
                <PolarAngleAxis dataKey="metric" tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.5)' }} />
                <Radar name="HydroGNN-Net" dataKey="A" stroke="#22d3ee" fill="#22d3ee" fillOpacity={0.15} strokeWidth={2} />
              </RadarChart>
            </ResponsiveContainer>
          </motion.div>
        </div>

        {/* Architecture diagram */}
        <div className="grid-2">
          <motion.div className="glass-card" style={{ padding: 24 }}
            initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}
          >
            <h3 style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: 16 }}>Model Architecture</h3>
            <ArchDiagram />
          </motion.div>

          <motion.div className="glass-card" style={{ padding: 24 }}
            initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }}
          >
            <h3 style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: 16 }}>Per-Station NSE Scores</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {STATIONS.map((s, i) => (
                <motion.div key={s.id} initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.5 + i * 0.06 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.6)' }}>{s.name}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: '#22d3ee', fontWeight: 600 }}>{s.nse.toFixed(3)}</span>
                  </div>
                  <div className="progress-track">
                    <motion.div
                      className="progress-fill"
                      style={{ width: 0 }}
                      animate={{ width: `${s.nse * 100}%` }}
                      transition={{ delay: 0.7 + i * 0.06, duration: 1 }}
                    />
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>
        </div>
      </div>
    </AppLayout>
  );
}
