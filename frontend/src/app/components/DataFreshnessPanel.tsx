'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { Activity, Clock, RefreshCw, CheckCircle2, AlertTriangle, Database } from 'lucide-react';

interface FreshnessItem {
  source: string;
  last_updated: string;
  status: 'Live' | 'Latest Available' | 'Stale';
  refresh_interval: string;
}

interface DataFreshnessPanelProps {
  freshnessData?: FreshnessItem[];
  onRefresh?: () => void;
}

export default function DataFreshnessPanel({ freshnessData = [], onRefresh }: DataFreshnessPanelProps) {
  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'Live':
        return {
          bg: 'rgba(16,185,129,0.12)',
          border: 'rgba(16,185,129,0.3)',
          color: '#34d399',
          icon: <CheckCircle2 size={12} color="#34d399" />,
          label: 'Live'
        };
      case 'Latest Available':
        return {
          bg: 'rgba(6,182,212,0.12)',
          border: 'rgba(6,182,212,0.3)',
          color: '#22d3ee',
          icon: <Activity size={12} color="#22d3ee" />,
          label: 'Latest Available'
        };
      default:
        return {
          bg: 'rgba(244,63,94,0.12)',
          border: 'rgba(244,63,94,0.3)',
          color: '#fb7185',
          icon: <AlertTriangle size={12} color="#fb7185" />,
          label: 'Stale'
        };
    }
  };

  return (
    <div className="glass-panel" style={{ padding: 20, borderRadius: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 10,
            background: 'rgba(56,189,248,0.12)', border: '1px solid rgba(56,189,248,0.25)',
            display: 'flex', alignItems: 'center', justifyContent: 'center'
          }}>
            <Database size={16} color="#38bdf8" />
          </div>
          <div>
            <h3 style={{ fontSize: '0.95rem', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
              Data Freshness & Ingestion Monitor
            </h3>
            <p style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.4)', margin: 0 }}>
              Real-time synchronization status across telemetry feeds
            </p>
          </div>
        </div>

        {onRefresh && (
          <button
            onClick={onRefresh}
            className="btn btn-secondary"
            style={{ padding: '6px 12px', fontSize: '0.75rem', gap: 6 }}
          >
            <RefreshCw size={13} /> Refresh Feeds
          </button>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
        {freshnessData.map((item, idx) => {
          const badge = getStatusBadge(item.status);
          return (
            <motion.div
              key={item.source}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.05 }}
              style={{
                background: 'rgba(15,23,42,0.45)',
                border: '1px solid rgba(255,255,255,0.06)',
                borderRadius: 12,
                padding: '12px 14px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between'
              }}
            >
              <div>
                <div style={{ fontSize: '0.82rem', fontWeight: 600, color: '#e2e8f0' }}>
                  {item.source}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
                  <Clock size={11} color="rgba(255,255,255,0.35)" />
                  <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.45)', fontFamily: 'var(--font-mono)' }}>
                    {item.last_updated}
                  </span>
                </div>
              </div>

              <div style={{ textAlign: 'right' }}>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 5,
                    padding: '3px 8px',
                    borderRadius: 6,
                    fontSize: '0.68rem',
                    fontWeight: 700,
                    background: badge.bg,
                    border: `1px solid ${badge.border}`,
                    color: badge.color
                  }}
                >
                  {badge.icon}
                  {badge.label}
                </span>
                <div style={{ fontSize: '0.62rem', color: 'rgba(255,255,255,0.3)', marginTop: 3 }}>
                  Interval: {item.refresh_interval}
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
