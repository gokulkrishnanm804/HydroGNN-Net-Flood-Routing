'use client';
import { motion, AnimatePresence } from 'framer-motion';
import { useState, useEffect, useMemo } from 'react';
import AppLayout from '../AppLayout';
import { GitBranch, Droplets, Clock, AlertTriangle, Play, Pause, RotateCcw, RefreshCw } from 'lucide-react';
import { api } from '../../services/api';
import { STATUS_CONFIG } from '../data/mockData';

/* ── Base static routing confluences schematic (Cauvery downstream order) ── */
const BASE_NODES = [
  { id: 'KABINI',       label: 'Kabini',       type: 'reservoir', status: 'alert',   level: 51.3,  capacity: 100, eta: 0,    desc: 'Origin reservoir — upstream surge source',        color: '#fbbf24' },
  { id: 'KRS',          label: 'KRS',          type: 'reservoir', status: 'warning', level: 97.3,  capacity: 100, eta: 1,    desc: 'Krishna Raja Sagara — 97% full, releasing',         color: '#fb923c' },
  { id: 'METTUR',       label: 'Mettur',       type: 'reservoir', status: 'alert',   level: 87.0,  capacity: 100, eta: 4,    desc: 'Mettur — controlled release recommended',           color: '#fbbf24' },
  { id: 'ERODE',        label: 'Erode',        type: 'station',   status: 'safe',    level: 28.1,  capacity: 65,  eta: 8,    desc: 'Erode gauge — below danger, monitoring',            color: '#34d399' },
  { id: 'KODUMUDI',     label: 'Kodumudi',     type: 'station',   status: 'safe',    level: 22.8,  capacity: 50,  eta: 11,   desc: 'Kodumudi — downstream of Erode, stable',           color: '#34d399' },
  { id: 'KARUR',        label: 'Karur',        type: 'station',   status: 'warning', level: 38.9,  capacity: 55,  eta: 14,   desc: 'Karur — rising trend, 70% capacity',                color: '#fb923c' },
  { id: 'MUSIRI',       label: 'Musiri',       type: 'station',   status: 'safe',    level: 19.4,  capacity: 45,  eta: 16,   desc: 'Musiri — currently safe, pre-alert',                color: '#22d3ee' },
  { id: 'TRICHY',       label: 'Trichy Upper', type: 'station',   status: 'danger',  level: 71.2,  capacity: 90,  eta: 18,   desc: 'Trichy Upper — CRITICAL 79% — EVACUATE RISK',       color: '#fb7185' },
  { id: 'GRAND_ANICUT', label: 'Grand Anicut', type: 'station',   status: 'safe',    level: 15.3,  capacity: 35,  eta: 22,   desc: 'Grand Anicut — terminus, safe for now',             color: '#34d399' },
];

const STATUS_META: Record<string, { color: string; glow: string; badge: string }> = {
  safe:    { color: '#34d399', glow: 'rgba(52,211,153,0.4)',   badge: 'badge-safe'    },
  alert:   { color: '#fbbf24', glow: 'rgba(251,191,36,0.4)',   badge: 'badge-alert'   },
  warning: { color: '#fb923c', glow: 'rgba(251,146,60,0.4)',   badge: 'badge-warning' },
  danger:  { color: '#fb7185', glow: 'rgba(251,113,133,0.5)',  badge: 'badge-danger'  },
};

/* Animated water droplet particle between two nodes */
function FlowParticle({ color, active, delay }: { color: string; active: boolean; delay: number }) {
  return (
    <AnimatePresence>
      {active && (
        <motion.div
          key={delay}
          style={{
            position: 'absolute', left: '50%', transform: 'translateX(-50%)',
            width: 8, height: 8, borderRadius: '50%',
            background: color, opacity: 0,
            boxShadow: `0 0 8px ${color}, 0 0 16px ${color}`,
            zIndex: 10,
          }}
          initial={{ top: '0%', opacity: 0, scale: 0.6 }}
          animate={{ top: '100%', opacity: [0, 1, 1, 0], scale: [0.6, 1, 1, 0.6] }}
          exit={{ opacity: 0 }}
          transition={{ duration: 1.2, delay, ease: 'linear', repeat: Infinity, repeatDelay: 0.4 }}
        />
      )}
    </AnimatePresence>
  );
}

function RoutingNode({ node, idx, selected, onSelect, playing }: {
  node: any; idx: number; selected: boolean; onSelect: () => void; playing: boolean;
}) {
  const sm = STATUS_META[node.status] || STATUS_META.safe;
  const pct = Math.round((node.level / node.capacity) * 100);
  const isLast = idx === BASE_NODES.length - 1;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', position: 'relative', width: '100%' }}>
      {/* Node card */}
      <motion.div
        onClick={onSelect}
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.1 + idx * 0.07, ease: [0.34, 1.2, 0.64, 1] }}
        whileHover={{ scale: 1.04, y: -2 }}
        whileTap={{ scale: 0.96 }}
        style={{
          width: '100%', cursor: 'pointer',
          background: selected ? `${sm.color}12` : 'rgba(10,22,50,0.6)',
          border: `1.5px solid ${selected ? sm.color + '50' : 'rgba(255,255,255,0.07)'}`,
          borderRadius: 14, padding: '14px 16px',
          boxShadow: selected ? `0 0 24px ${sm.glow}, 0 8px 32px rgba(0,0,0,0.4)` : 'none',
          backdropFilter: 'blur(16px)',
          transition: 'all 0.25s',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
          <div style={{ position: 'relative', flexShrink: 0 }}>
            <motion.div
              style={{
                width: 38, height: 38, borderRadius: '50%',
                background: `radial-gradient(circle, ${sm.color}30, transparent 70%)`,
                border: `2px solid ${sm.color}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                boxShadow: `0 0 12px ${sm.color}60`,
              }}
              animate={{
                boxShadow: selected
                  ? [`0 0 12px ${sm.color}60`, `0 0 24px ${sm.color}90`, `0 0 12px ${sm.color}60`]
                  : `0 0 8px ${sm.color}40`,
              }}
              transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
            >
              {node.type === 'reservoir'
                ? <Droplets size={15} color={sm.color} />
                : <div style={{ width: 6, height: 6, borderRadius: '50%', background: sm.color }} />
              }
            </motion.div>
          </div>
          <div>
            <div style={{ fontSize: '0.85rem', fontWeight: 800, color: '#e2e8f0', display: 'flex', alignItems: 'center', gap: 8 }}>
              {node.label}
              <span className={`badge ${sm.badge}`} style={{ fontSize: '0.58rem', padding: '1px 6px' }}>{node.status}</span>
            </div>
            <div style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.35)', marginTop: 1 }}>
              {node.type === 'reservoir' ? 'Reservoir Storage' : 'Downstream Gauge'}
            </div>
          </div>
          <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.92rem', fontWeight: 800, color: sm.color }}>{node.level.toFixed(1)}m</div>
            <div style={{ fontSize: '0.62rem', color: 'rgba(255,255,255,0.3)', marginTop: 1 }}>{pct}% cap</div>
          </div>
        </div>

        {/* Mini progress line */}
        <div style={{ height: 2, background: 'rgba(255,255,255,0.06)', borderRadius: 2, overflow: 'hidden' }}>
          <motion.div style={{ height: '100%', background: sm.color, width: 0 }}
            animate={{ width: `${pct}%` }} transition={{ duration: 1 }} />
        </div>
      </motion.div>

      {/* Link line to next node */}
      {!isLast && (
        <div style={{ width: 2, height: 32, background: 'rgba(255,255,255,0.06)', position: 'relative', overflow: 'visible' }}>
          <FlowParticle color={sm.color} active={playing} delay={idx * 0.15} />
        </div>
      )}
    </div>
  );
}

export default function RoutingPage() {
  const [selected, setSelected] = useState<string | null>('METTUR');
  const [playing, setPlaying] = useState(true);
  const [nodes, setNodes] = useState<any[]>(BASE_NODES);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [hasError, setHasError] = useState<boolean>(false);

  const fetchLiveConfluences = async () => {
    try {
      setIsLoading(true);
      setHasError(false);
      await api.login();
      const dash = await api.getDashboard();
      
      // Merge live database levels
      const merged = BASE_NODES.map(node => {
        if (node.type === 'reservoir') {
          const live = dash.reservoirs.find(r => r.id === node.id);
          if (live) {
            const pct = live.storage_pct;
            const severity = pct > 90 ? 'danger' : pct > 80 ? 'warning' : pct > 65 ? 'alert' : 'safe';
            return {
              ...node,
              level: live.current_storage_mcft,
              capacity: live.capacity_mcft,
              status: severity,
              color: STATUS_CONFIG[severity].color,
              desc: `${node.label} reservoir storage currently active at ${pct.toFixed(0)}% fill capacity. Inflow is convolved downstream.`,
            };
          }
        } else {
          // If station is Grand Anicut, map to TANJORE
          const matchId = node.id === 'GRAND_ANICUT' ? 'TANJORE' : node.id;
          const live = dash.stations.find(s => s.id === matchId);
          if (live) {
            const pct = (live.water_level / live.danger_level) * 100;
            const rawStatus = (live.risk_level || 'Safe').toLowerCase();
            const severity = rawStatus === 'severe flood' || rawStatus === 'high risk' ? 'danger' : rawStatus === 'moderate risk' ? 'warning' : rawStatus === 'low risk' ? 'alert' : 'safe';
            return {
              ...node,
              level: live.water_level,
              capacity: live.danger_level,
              status: severity,
              color: STATUS_CONFIG[severity].color,
              desc: `${node.label} CWC telemetry point currently tracking at ${live.water_level.toFixed(2)}ft (Danger: ${live.danger_level.toFixed(1)}ft). Risk status: ${live.risk_level || 'Normal'}.`,
            };
          }
        }
        return node;
      });
      setNodes(merged);
    } catch (err) {
      console.error('Failed to query routing confluences:', err);
      setHasError(true);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchLiveConfluences();
  }, []);

  const sel = nodes.find(n => n.id === selected) || nodes[2];

  // Count active warnings in the live nodes
  const nodesAtRisk = useMemo(() => {
    return nodes.filter(n => n.status === 'warning' || n.status === 'danger').length;
  }, [nodes]);

  if (isLoading) {
    return (
      <AppLayout>
        <div style={{ padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div style={{ height: 120, background: 'rgba(255,255,255,0.03)', borderRadius: 20 }} className="shimmer" />
          <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: 20 }}>
            <div style={{ height: 400, background: 'rgba(255,255,255,0.03)', borderRadius: 20 }} className="shimmer" />
            <div style={{ height: 400, background: 'rgba(255,255,255,0.03)', borderRadius: 20 }} className="shimmer" />
          </div>
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
          <h3 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#e2e8f0' }}>Flood Routing Offline</h3>
          <button className="btn btn-primary" onClick={fetchLiveConfluences}>
            <RefreshCw size={14} /> Retry
          </button>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div style={{ padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 20 }}>

        {/* Hero banner */}
        <motion.div className="glass-card gradient-border" style={{ padding: 24 }}
          initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16 }}>
            <div>
              <div style={{ fontSize: '0.7rem', color: '#22d3ee', letterSpacing: '0.1em', fontWeight: 800, textTransform: 'uppercase', marginBottom: 6 }}>SIMULATION ENGINE</div>
              <h1 className="gradient-text" style={{ fontSize: '1.5rem', fontWeight: 900, letterSpacing: '-0.03em', margin: 0 }}>
                Downstream Wave Propagation
              </h1>
              <p style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.45)', marginTop: 4, maxWidth: 420 }}>
                Calculates travel lag, wave speed, attenuation, and spillway release impacts across the Cauvery basin chain.
              </p>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <motion.button className="btn btn-primary" style={{ fontSize: '0.82rem', padding: '7px 16px', gap: 6 }}
                onClick={() => setPlaying(!playing)}
                whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.92 }}
              >
                {playing ? <><Pause size={14} />Pause</> : <><Play size={14} />Simulate</>}
              </motion.button>
              <motion.button className="btn btn-ghost" style={{ fontSize: '0.82rem', padding: '7px 14px' }}
                whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.92 }}
                onClick={() => { setPlaying(false); setTimeout(() => setPlaying(true), 100); }}
              >
                <RotateCcw size={14} />Reset
              </motion.button>
            </div>
          </div>

          {/* Stats row */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginTop: 20 }}>
            {[
              { label: 'Flood Wave Speed', value: '~2.4 m/s', color: '#22d3ee' },
              { label: 'Travel Time',      value: '~22 hours', color: '#a78bfa' },
              { label: 'Nodes at Risk',    value: `${nodesAtRisk} nodes`, color: nodesAtRisk > 0 ? '#fb7185' : '#34d399' },
              { label: 'Peak Estimated',   value: 'Trichy +6h', color: '#fb923c' },
            ].map(s => (
              <div key={s.label} style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 12, padding: '12px 14px', border: '1px solid rgba(255,255,255,0.06)' }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.95rem', fontWeight: 800, color: s.color }}>{s.value}</div>
                <div style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.35)', marginTop: 3, textTransform: 'uppercase', letterSpacing: '0.07em' }}>{s.label}</div>
              </div>
            ))}
          </div>
        </motion.div>

        <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: 20 }}>

          {/* Left — routing chain */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
            {nodes.map((node, idx) => (
              <RoutingNode key={node.id} node={node} idx={idx}
                selected={selected === node.id}
                onSelect={() => setSelected(s => s === node.id ? null : node.id)}
                playing={playing}
              />
            ))}
          </div>

          {/* Right — detail panel + surge chart */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

            {/* Selected node detail */}
            <AnimatePresence mode="wait">
              {sel ? (
                <motion.div
                  key={sel.id}
                  className="glass-card"
                  style={{ padding: '22px 24px', border: `1px solid ${sel.color}30` }}
                  initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -8 }}
                  transition={{ duration: 0.25 }}
                >
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16, marginBottom: 20 }}>
                    <motion.div
                      style={{
                        width: 56, height: 56, borderRadius: '50%',
                        background: `radial-gradient(circle, ${sel.color}20, transparent)`,
                        border: `2px solid ${sel.color}`,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        boxShadow: `0 0 24px ${sel.color}50`,
                        flexShrink: 0,
                      }}
                      animate={{ boxShadow: [`0 0 24px ${sel.color}50`, `0 0 40px ${sel.color}80`, `0 0 24px ${sel.color}50`] }}
                      transition={{ duration: 2, repeat: Infinity }}
                    >
                      <Droplets size={22} color={sel.color} />
                    </motion.div>
                    <div>
                      <div style={{ fontSize: '1.3rem', fontWeight: 900, color: 'rgba(255,255,255,0.95)', letterSpacing: '-0.03em' }}>{sel.label}</div>
                      <div style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.4)', marginTop: 2 }}>{sel.type === 'reservoir' ? 'Storage Reservoir' : 'CWC Gauge Station'} · Cauvery Basin</div>
                      <p style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.6)', marginTop: 8, lineHeight: 1.55, maxWidth: 420 }}>{sel.desc}</p>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
                    {[
                      { label: 'Current Level', value: `${sel.level.toFixed(1)}${sel.type === 'reservoir' ? ' MCFT' : 'ft'}`, color: sel.color },
                      { label: 'Capacity',       value: `${Math.round((sel.level / sel.capacity) * 100)}%`, color: sel.color },
                      { label: 'Wave ETA',       value: sel.eta === 0 ? 'ORIGIN' : `+${sel.eta} hrs`, color: '#22d3ee' },
                    ].map(m => (
                      <div key={m.label} style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 12, padding: '14px 16px', border: '1px solid rgba(255,255,255,0.06)', textAlign: 'center' }}>
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.2rem', fontWeight: 800, color: m.color }}>{m.value}</div>
                        <div style={{ fontSize: '0.62rem', color: 'rgba(255,255,255,0.3)', marginTop: 3, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{m.label}</div>
                      </div>
                    ))}
                  </div>

                  {/* Capacity bar */}
                  <div style={{ marginTop: 20 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                      <span style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.4)' }}>Fill Level</span>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: sel.color }}>{sel.level.toFixed(1)} / {sel.capacity.toFixed(0)} {sel.type === 'reservoir' ? 'MCFT' : 'm'}</span>
                    </div>
                    <div className="progress-track thick">
                      <motion.div
                        className="progress-fill"
                        style={{ background: `linear-gradient(90deg, ${sel.color}60, ${sel.color})`, width: 0 }}
                        animate={{ width: `${Math.min(100, (sel.level / sel.capacity) * 100)}%` }}
                        transition={{ duration: 1.5, ease: [0.34, 1.2, 0.64, 1] }}
                      />
                    </div>
                    {/* Danger markers */}
                    <div style={{ position: 'relative', height: 0, marginTop: -5, overflow: 'visible' }}>
                      <div style={{ position: 'absolute', left: '75%', top: -14, width: 1, height: 14, background: '#fb7185', opacity: 0.6 }} />
                      <div style={{ position: 'absolute', left: '75%', top: -24, fontSize: '0.58rem', color: '#fb7185', transform: 'translateX(-50%)' }}>75%</div>
                    </div>
                  </div>
                </motion.div>
              ) : (
                <motion.div key="empty"
                  className="glass-card"
                  style={{ padding: '40px', textAlign: 'center', color: 'rgba(255,255,255,0.25)' }}
                  initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                >
                  <GitBranch size={32} style={{ margin: '0 auto 12px', opacity: 0.3 }} />
                  <p style={{ color: 'rgba(255,255,255,0.25)', fontSize: '0.85rem' }}>Select a node to view details</p>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Wave propagation timeline */}
            <motion.div className="glass-card" style={{ padding: '22px 24px' }}
              initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }}
            >
              <div style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: 16, letterSpacing: '-0.01em' }}>
                Flood Wave Propagation Timeline
              </div>
              <div style={{ position: 'relative', paddingLeft: 20 }}>
                {/* Vertical timeline line */}
                <div style={{ position: 'absolute', left: 8, top: 8, bottom: 8, width: 2, background: 'linear-gradient(180deg, #22d3ee, #fb7185, #34d399)', borderRadius: 2, opacity: 0.4 }} />
                {nodes.map((n, i) => {
                  const sm = STATUS_META[n.status] || STATUS_META.safe;
                  return (
                    <motion.div key={n.id}
                      onClick={() => setSelected(n.id)}
                      initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: 0.6 + i * 0.06 }}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 12,
                        padding: '9px 12px', marginBottom: 6,
                        borderRadius: 10, cursor: 'pointer',
                        background: selected === n.id ? `${sm.color}0a` : 'transparent',
                        border: `1px solid ${selected === n.id ? sm.color + '25' : 'transparent'}`,
                        transition: 'all 0.2s',
                      }}
                      whileHover={{ background: `${sm.color}0d`, paddingLeft: '16px' }}
                    >
                      <motion.div style={{ width: 10, height: 10, borderRadius: '50%', background: sm.color, flexShrink: 0, boxShadow: `0 0 8px ${sm.color}` }}
                        animate={{ scale: n.status === 'danger' ? [1, 1.4, 1] : 1 }}
                        transition={{ duration: 0.8, repeat: Infinity }}
                      />
                      <div style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.7)', fontWeight: 600, flex: 1 }}>{n.label}</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'rgba(255,255,255,0.3)' }}>
                        {n.eta === 0 ? '00:00' : `+${String(n.eta).padStart(2,'0')}:00`}
                      </div>
                      <span className={`badge ${sm.badge}`} style={{ fontSize: '0.58rem', padding: '1px 7px' }}>{n.status}</span>
                    </motion.div>
                  );
                })}
              </div>
            </motion.div>

            {/* AI prediction note */}
            <motion.div
              style={{
                background: 'rgba(251,113,133,0.07)', border: '1px solid rgba(251,113,133,0.2)',
                borderRadius: 14, padding: '16px 18px',
                display: 'flex', alignItems: 'flex-start', gap: 12,
              }}
              initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.8 }}
            >
              <motion.div animate={{ rotate: [0,-8,8,-5,5,0] }} transition={{ duration: 1, repeat: Infinity, repeatDelay: 5 }}>
                <AlertTriangle size={18} color="#fb7185" />
              </motion.div>
              <div>
                <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#fb7185', marginBottom: 4 }}>AI Warning — HydroGNN-Net</div>
                <p style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.58)', margin: 0, lineHeight: 1.6 }}>
                  Flood wave from Kabini will reach <strong style={{ color: '#fb7185' }}>Trichy Upper in ~18 hours</strong>. 
                  Current trajectory shows high risk probability of exceeding danger threshold. 
                  <strong style={{ color: '#fbbf24' }}> Immediate downstream alert recommended.</strong>
                </p>
              </div>
            </motion.div>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
