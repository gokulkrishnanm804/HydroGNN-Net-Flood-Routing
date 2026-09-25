'use client';
import React, { useState, useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { RefreshCw, CheckCircle, Clock } from 'lucide-react';
import { api } from '../../services/api';

const PAGE_META: Record<string, { title: string; desc: string }> = {
  '/': { title: 'Basin Monitoring Overview', desc: 'Real-time telemetry and flood risk status across the Cauvery River Basin' },
  '/stations': { title: 'Station Monitoring', desc: 'Observed stages and operational threshold tracking for monitored gauges' },
  '/forecast': { title: 'HydroGNN-Net Forecast', desc: 'Native 6h, 12h, and 24h multi-horizon water-level predictions with uncertainty' },
  '/routing': { title: 'Flood Wave Routing', desc: 'Upstream-to-downstream topological flood propagation and reach travel timing' },
  '/alerts': { title: 'Flood Warning Center', desc: 'Actionable hydrological hazard notices and advisory actions' },
  '/model': { title: 'AI Model & Verification', desc: 'Spatio-Temporal Graph Neural Network architecture and held-out test evaluation' },
  '/reports': { title: 'Basin Operational Reports', desc: 'Executive summaries and station monitoring bulletins' },
  '/diagnostics': { title: 'System & Diagnostics', desc: 'Backend health, model loader verification, and data ingestion freshness' },
};

export default function TopBar() {
  const pathname = usePathname();
  const [istTime, setIstTime] = useState<string>('');
  const [modelStatus, setModelStatus] = useState<string>('Checking...');
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      const options: Intl.DateTimeFormatOptions = {
        timeZone: 'Asia/Kolkata',
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      };
      setIstTime(new Intl.DateTimeFormat('en-IN', options).format(now) + ' IST');
    };

    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    let isMounted = true;
    const checkHealth = async () => {
      try {
        const health = await api.getHealth();
        if (isMounted) {
          setModelStatus(health.model_status === 'Loaded' ? 'Exp 9 Active (CPU)' : health.model_status);
        }
      } catch {
        if (isMounted) setModelStatus('Backend Offline');
      }
    };
    checkHealth();
  }, []);

  const meta = PAGE_META[pathname] || { title: 'HydroGNN-Net', desc: 'Cauvery River Flood Routing' };

  const handleRefresh = () => {
    setIsRefreshing(true);
    window.location.reload();
  };

  return (
    <header
      style={{
        height: 58,
        backgroundColor: '#0a1020',
        borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 24px',
        width: '100%',
        boxSizing: 'border-box',
      }}
    >
      {/* Page Title & Breadcrumb */}
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <h1 style={{ fontSize: '0.98rem', fontWeight: 600, color: '#f8fafc', margin: 0, lineHeight: 1.2 }}>
          {meta.title}
        </h1>
        <span style={{ fontSize: '0.72rem', color: '#94a3b8', lineHeight: 1.2 }}>
          {meta.desc}
        </span>
      </div>

      {/* Right Actions / System Status */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        {/* Model Status Pill */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            backgroundColor: 'rgba(16, 185, 129, 0.08)',
            border: '1px solid rgba(16, 185, 129, 0.22)',
            borderRadius: 4,
            padding: '3px 9px',
            fontSize: '0.72rem',
            color: '#10b981',
            fontWeight: 500,
          }}
        >
          <CheckCircle size={12} color="#10b981" />
          <span>{modelStatus}</span>
        </div>

        {/* IST Clock */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 5,
            fontSize: '0.74rem',
            color: '#94a3b8',
            fontFamily: 'var(--font-mono)',
            padding: '3px 8px',
            backgroundColor: 'rgba(255, 255, 255, 0.03)',
            borderRadius: 4,
            border: '1px solid rgba(255, 255, 255, 0.06)',
          }}
        >
          <Clock size={12} color="#64748b" />
          <span>{istTime || 'Loading time...'}</span>
        </div>

        {/* Refresh Button */}
        <button
          onClick={handleRefresh}
          className="btn btn-secondary btn-sm"
          title="Refresh real-time data"
          style={{ padding: '4px 9px' }}
        >
          <RefreshCw size={12} className={isRefreshing ? 'spin' : ''} />
          <span style={{ fontSize: '0.72rem' }}>Refresh</span>
        </button>
      </div>
    </header>
  );
}
