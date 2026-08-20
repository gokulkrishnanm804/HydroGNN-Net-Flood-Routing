'use client';
import { motion, AnimatePresence } from 'framer-motion';
import { useState, useEffect, useMemo } from 'react';
import { Brain, Zap, AlertTriangle, CheckCircle, ChevronRight, Activity } from 'lucide-react';

interface Props {
  liveSupportText?: any; // Reads the decision_support dict from /api/dashboard
}

const SEVERITY_STYLES: Record<string, { border: string; bg: string; badge: string; dot: string }> = {
  danger:  { border: 'rgba(251,113,133,0.25)', bg: 'rgba(251,113,133,0.05)', badge: 'badge-danger', dot: 'status-danger' },
  warning: { border: 'rgba(251,146,60,0.25)',  bg: 'rgba(251,146,60,0.05)',  badge: 'badge-warning', dot: 'status-warning' },
  alert:   { border: 'rgba(251,191,36,0.20)',  bg: 'rgba(251,191,36,0.04)', badge: 'badge-alert',   dot: 'status-alert' },
};

export default function AICommandCenter({ liveSupportText }: Props) {
  const [activeRec, setActiveRec] = useState(0);
  const [inferenceTime, setInferenceTime] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setInferenceTime(s => (s + 1) % 600), 1000);
    return () => clearInterval(t);
  }, []);

  const mins = Math.floor(inferenceTime / 60);
  const secs = inferenceTime % 60;

  // Process live recommendations from backend support dictionary
  const recommendations = useMemo(() => {
    if (!liveSupportText) return [];

    const list: any[] = [];
    let idCounter = 1;

    // 1. Map Reservoir Control recommendations
    const controls = liveSupportText.reservoir_controls || [];
    controls.forEach((c: any) => {
      const priority = (c.priority_level || 'Routine').toLowerCase();
      const severity = priority === 'critical' ? 'danger' : priority === 'warning' ? 'warning' : 'alert';
      
      list.push({
        id: idCounter++,
        severity,
        icon: '🌊',
        title: `Reservoir Control — ${c.reservoir_id}`,
        body: `${c.recommended_action} Storage is currently at ${c.storage_pct.toFixed(1)}% capacity with an expected inflow of ${c.predicted_inflow.toFixed(1)} cumecs.`,
        confidence: severity === 'danger' ? 92 : severity === 'warning' ? 88 : 84,
        time: 'Live',
      });
    });

    // 2. Map Road Closures
    const closures = liveSupportText.road_closures || [];
    closures.forEach((rc: any) => {
      list.push({
        id: idCounter++,
        severity: rc.status === 'CLOSED' ? 'danger' : 'warning',
        icon: '🚧',
        title: `Road Closure: ${rc.road}`,
        body: `${rc.reason}. Operational status check: ${rc.status}. Divert local traffic routes.`,
        confidence: rc.status === 'CLOSED' ? 90 : 85,
        time: 'Live',
      });
    });

    // 3. Map Evacuation Rankings
    const evacs = liveSupportText.evacuation_rankings || [];
    evacs.forEach((e: any) => {
      list.push({
        id: idCounter++,
        severity: e.status === 'IMMEDIATE' ? 'danger' : 'warning',
        icon: '🚨',
        title: `Evacuation — ${e.district}`,
        body: `Emergency level: ${e.status}. GNN analysis detected ${e.high_risk_stations_count} critical stations at flood-risk within local boundaries. Allocate shelters immediately.`,
        confidence: e.status === 'IMMEDIATE' ? 94 : 86,
        time: 'Live',
      });
    });

    // Fallback if everything is nominal
    if (list.length === 0) {
      list.push({
        id: idCounter++,
        severity: 'alert',
        icon: '✅',
        title: 'Optimal Basin Routing',
        body: 'All reservoir levels and flows are nominal. No emergency gate controls, evacuation alerts, or road closures are required at this telemetry tick.',
        confidence: 95,
        time: 'Live',
      });
    }

    return list;
  }, [liveSupportText]);

  const activeWarningsCount = useMemo(() => {
    if (!liveSupportText) return 0;
    const evacCount = (liveSupportText.evacuation_rankings || []).length;
    const roadCount = (liveSupportText.road_closures || []).length;
    return evacCount + roadCount;
  }, [liveSupportText]);

  return (
    <motion.div
      style={{
        background: 'rgba(10,22,50,0.7)',
        border: '1px solid rgba(34,211,238,0.18)',
        borderRadius: 20,
        overflow: 'hidden',
        position: 'relative',
      }}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.4 }}
    >
      {/* Top glow bar */}
      <div style={{ height: 2, background: 'linear-gradient(90deg, transparent, #22d3ee 30%, #34d399 70%, transparent)', opacity: 0.7 }} />

      {/* Header */}
      <div style={{ padding: '16px 20px 12px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div className="ring-spinner" style={{ width: 44, height: 44, flexShrink: 0 }}>
            <Brain size={18} color="#22d3ee" />
          </div>
          <div>
            <div style={{ fontSize: '0.92rem', fontWeight: 800, color: '#e2e8f0', letterSpacing: '-0.02em' }}>
              AI Command Center
            </div>
            <div style={{ fontSize: '0.68rem', color: 'rgba(255,255,255,0.38)', marginTop: 1 }}>
              HydroGNN-Net v2.4 · Live inference
            </div>
          </div>
          <span className="badge badge-safe" style={{ marginLeft: 'auto', fontSize: '0.62rem' }}>
            <span className="status-dot status-safe" style={{ width: 5, height: 5 }} />
            ACTIVE
          </span>
        </div>

        {/* Metrics row */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginTop: 14 }}>
          {[
            { label: 'Confidence', value: '89.1%', color: '#22d3ee', sub: 'weighted' },
            { label: 'Last Run',   value: `${mins}:${String(secs).padStart(2,'0')}`, color: '#34d399', sub: 'ago' },
            { label: 'Alerts',    value: String(activeWarningsCount), color: activeWarningsCount > 0 ? '#fb7185' : '#34d399', sub: 'active' },
          ].map(m => (
            <div key={m.label} style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 10, padding: '9px 10px', textAlign: 'center' }}>
              <div style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: '1rem', fontWeight: 700, color: m.color }}>{m.value}</div>
              <div style={{ fontSize: '0.62rem', color: 'rgba(255,255,255,0.35)', marginTop: 2, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{m.label}</div>
            </div>
          ))}
        </div>

        {/* Processing bar */}
        <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Activity size={11} color="#22d3ee" />
          <span style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.35)' }}>Model health</span>
          <div style={{ flex: 1, height: 3, background: 'rgba(255,255,255,0.06)', borderRadius: 4, overflow: 'hidden' }}>
            <div className="ai-gradient-bar" style={{ height: '100%', width: '89%', borderRadius: 4 }} />
          </div>
          <span style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: '0.68rem', color: '#34d399' }}>89%</span>
        </div>
      </div>

      {/* Recommendations */}
      <div style={{ padding: '12px 16px 16px' }}>
        <div style={{ fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'rgba(255,255,255,0.28)', marginBottom: 10 }}>
          AI RECOMMENDATIONS
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {recommendations.map((r: any, i: number) => {
            const s = SEVERITY_STYLES[r.severity] || SEVERITY_STYLES.alert;
            const isActive = activeRec === i;
            return (
              <motion.div
                key={r.id}
                onClick={() => setActiveRec(isActive ? -1 : i)}
                style={{
                  border: `1px solid ${s.border}`,
                  background: s.bg,
                  borderRadius: 12, padding: '11px 14px',
                  cursor: 'pointer',
                  transition: 'border-color 0.2s',
                }}
                whileHover={{ borderColor: s.border.replace('0.25', '0.5'), scale: 1.005 }}
                whileTap={{ scale: 0.995 }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                  <span style={{ fontSize: '1rem', flexShrink: 0 }}>{r.icon}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'rgba(255,255,255,0.88)', lineHeight: 1.3, display: 'flex', alignItems: 'center', gap: 6, textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                      {r.title}
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                    <span style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: '0.7rem', color: '#22d3ee', fontWeight: 700 }}>{r.confidence}%</span>
                    <motion.div animate={{ rotate: isActive ? 90 : 0 }} transition={{ duration: 0.2 }}>
                      <ChevronRight size={13} color="rgba(255,255,255,0.35)" />
                    </motion.div>
                  </div>
                </div>

                <AnimatePresence>
                  {isActive && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.25 }}
                      style={{ overflow: 'hidden' }}
                    >
                      <p style={{ fontSize: '0.76rem', color: 'rgba(255,255,255,0.6)', lineHeight: 1.6, marginTop: 8, paddingTop: 8, borderTop: '1px solid rgba(255,255,255,0.06)', margin: '8px 0 0' }}>
                        {r.body}
                      </p>
                      <div style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.28)', marginTop: 6 }}>Confidence: {r.confidence}% · {r.time}</div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            );
          })}
        </div>
      </div>
    </motion.div>
  );
}
