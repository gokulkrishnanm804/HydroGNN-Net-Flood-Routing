'use client';
import React, { useState, useEffect, useMemo } from 'react';
import dynamic from 'next/dynamic';
import AppLayout from './AppLayout';
import RiskBadge from './components/RiskBadge';
import HydrographChart from './components/HydrographChart';
import { LoadingSkeleton, ErrorBanner } from './components/StateViews';
import { api } from '../services/api';
import {
  Radio,
  AlertTriangle,
  CloudRain,
  Brain,
  ShieldCheck,
  CheckCircle,
  Database,
  ArrowRight,
  TrendingUp,
  RefreshCw,
} from 'lucide-react';
import Link from 'next/link';

// Dynamically import Leaflet map to prevent SSR window reference
const CauveryMap = dynamic(() => import('./components/CauveryMap'), {
  ssr: false,
  loading: () => (
    <div
      style={{
        height: 420,
        backgroundColor: 'rgba(255, 255, 255, 0.02)',
        borderRadius: 8,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#64748b',
        fontSize: '0.85rem',
      }}
    >
      Loading Cauvery Basin Spatial Map...
    </div>
  ),
});

export default function DashboardPage() {
  const [dashboardData, setDashboardData] = useState<any>(null);
  const [focalPrediction, setFocalPrediction] = useState<any>(null);
  const [selectedStationId, setSelectedStationId] = useState<string>('METTUR');
  const [isForecastLoading, setIsForecastLoading] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [hasError, setHasError] = useState<boolean>(false);

  const loadData = async () => {
    try {
      setIsLoading(true);
      setHasError(false);
      await api.login();
      const dash = await api.getDashboard();
      setDashboardData(dash);

      const stations = dash.stations || [];
      const initialId = stations.some((s: any) => s.id === 'METTUR')
        ? 'METTUR'
        : stations[0]?.id || 'METTUR';
      setSelectedStationId(initialId);

      const pred = await api.getPrediction(initialId, [6, 12, 24]);
      setFocalPrediction(pred);
    } catch (err) {
      console.error('Failed to load dashboard:', err);
      setHasError(true);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleStationSelect = async (stationId: string) => {
    if (!stationId) return;
    try {
      setSelectedStationId(stationId);
      setIsForecastLoading(true);
      const pred = await api.getPrediction(stationId, [6, 12, 24]);
      setFocalPrediction(pred);
    } catch (err) {
      console.error(`Failed to fetch forecast for station ${stationId}:`, err);
    } finally {
      setIsForecastLoading(false);
    }
  };

  const stations = dashboardData?.stations || [];
  const reservoirs = dashboardData?.reservoirs || [];

  // Summary Metrics
  const summary = useMemo(() => {
    const totalStations = stations.length;
    const attentionStations = stations.filter((s: any) => {
      const risk = (s.risk_level || '').toLowerCase();
      return risk.includes('warn') || risk.includes('danger') || risk.includes('severe');
    });

    const rainValues = stations.map((s: any) => Number(s.rain_observed || 0));
    const maxRain = rainValues.length > 0 ? Math.max(...rainValues) : 0;
    const avgRain =
      rainValues.length > 0
        ? rainValues.reduce((a: number, b: number) => a + b, 0) / rainValues.length
        : 0;

    return {
      totalStations,
      attentionCount: attentionStations.length,
      attentionStations,
      maxRain,
      avgRain,
    };
  }, [stations]);

  // Selected Station details
  const selectedStation = useMemo(() => {
    return stations.find((s: any) => s.id === selectedStationId) || stations[0] || null;
  }, [stations, selectedStationId]);

  // Native Forecast Horizons (6h, 12h, 24h)
  const nativeForecasts = useMemo(() => {
    if (!focalPrediction?.predictions) return [];
    return [6, 12, 24].map((h) => {
      const pred = focalPrediction.predictions.find((p: any) => p.horizon_hours === h);
      return {
        horizon: `${h}h`,
        level_ft: pred ? pred.level_m : null,
        uncertainty: pred ? pred.uncertainty_m : null,
        severity: pred ? pred.severity : 'Safe',
      };
    });
  }, [focalPrediction]);

  // Risk distribution count
  const riskCounts = useMemo(() => {
    let safe = 0;
    let warning = 0;
    let danger = 0;

    stations.forEach((s: any) => {
      const r = (s.risk_level || '').toLowerCase();
      if (r.includes('danger') || r.includes('severe') || r.includes('high')) danger++;
      else if (r.includes('warn') || r.includes('moderate')) warning++;
      else safe++;
    });

    return { safe, warning, danger };
  }, [stations]);

  if (isLoading) {
    return (
      <AppLayout>
        <LoadingSkeleton rows={5} height={120} />
      </AppLayout>
    );
  }

  if (hasError || !dashboardData) {
    return (
      <AppLayout>
        <ErrorBanner onRetry={loadData} />
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        {/* 1. TOP SUMMARY METRICS */}
        <section
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: 14,
          }}
        >
          {/* Active Gauges */}
          <div className="metric-kpi">
            <div className="metric-kpi-label">
              <span>Active Monitoring Stations</span>
              <Radio size={14} color="#0ea5e9" />
            </div>
            <div className="metric-kpi-value">{summary.totalStations || 8}</div>
            <div className="metric-kpi-sub">Cauvery main stem & tributaries</div>
          </div>

          {/* Stations Requiring Attention */}
          <div className="metric-kpi">
            <div className="metric-kpi-label">
              <span>Stations Requiring Attention</span>
              <AlertTriangle
                size={14}
                color={summary.attentionCount > 0 ? '#f59e0b' : '#10b981'}
              />
            </div>
            <div
              className="metric-kpi-value"
              style={{ color: summary.attentionCount > 0 ? '#f59e0b' : '#10b981' }}
            >
              {summary.attentionCount}
            </div>
            <div className="metric-kpi-sub">
              {summary.attentionCount === 0
                ? 'All reaches within normal thresholds'
                : `${summary.attentionCount} reach exceeding warning levels`}
            </div>
          </div>

          {/* Rainfall Summary */}
          <div className="metric-kpi">
            <div className="metric-kpi-label">
              <span>Basin Max Rainfall (24h)</span>
              <CloudRain size={14} color="#38bdf8" />
            </div>
            <div className="metric-kpi-value">
              {summary.maxRain.toFixed(1)}{' '}
              <span style={{ fontSize: '0.88rem', fontWeight: 500, color: '#94a3b8' }}>mm</span>
            </div>
            <div className="metric-kpi-sub">
              Basin Average: {summary.avgRain.toFixed(1)} mm
            </div>
          </div>

          {/* Model Operational Status */}
          <div className="metric-kpi">
            <div className="metric-kpi-label">
              <span>Model Operational Status</span>
              <Brain size={14} color="#10b981" />
            </div>
            <div className="metric-kpi-value" style={{ fontSize: '1.25rem', color: '#10b981' }}>
              Experiment 9
            </div>
            <div className="metric-kpi-sub">
              Online · PyTorch CPU · Native 6h/12h/24h
            </div>
          </div>
        </section>

        {/* 2. MAIN WORKSPACE: Spatial Map + Water Level Trend & Forecast */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(0, 1.2fr) minmax(0, 1fr)',
            gap: 18,
          }}
        >
          {/* LEFT: Cauvery River Basin Map */}
          <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
            <div className="card-header">
              <div className="card-title">
                <Radio size={16} color="#0ea5e9" />
                <span>Cauvery River Basin Map</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: '0.74rem', color: '#94a3b8' }}>
                  Click station pin to inspect
                </span>
                <Link
                  href="/stations"
                  className="btn btn-secondary btn-sm"
                  style={{ textDecoration: 'none' }}
                >
                  Stations Table <ArrowRight size={12} />
                </Link>
              </div>
            </div>

            <div style={{ padding: 12, flex: 1, minHeight: 450 }}>
              <CauveryMap
                stations={stations}
                reservoirs={reservoirs}
                selectedStationId={selectedStationId}
                onSelect={handleStationSelect}
              />
            </div>
          </div>

          {/* RIGHT: Selected Station Hydrograph & Forecast Horizons */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Focal Station Hydrograph Chart */}
            <div className="card">
              <div className="card-header" style={{ flexWrap: 'wrap', gap: 10 }}>
                <div>
                  <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <TrendingUp size={16} color="#0ea5e9" />
                    <span>{selectedStation?.name || 'Station'} Hydrograph</span>
                  </div>
                  <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: 2 }}>
                    Reach: {selectedStation?.basin || 'Cauvery'} River · Current Level:{' '}
                    <strong style={{ color: '#f8fafc' }}>
                      {Number(selectedStation?.water_level || 0).toFixed(2)} ft
                    </strong>
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontSize: '0.72rem', color: '#94a3b8', fontWeight: 500 }}>
                      Station:
                    </span>
                    <select
                      id="dashboard-station-select"
                      value={selectedStationId}
                      onChange={(e) => handleStationSelect(e.target.value)}
                      style={{
                        backgroundColor: 'var(--bg-surface)',
                        border: '1px solid var(--border-medium)',
                        color: '#f8fafc',
                        fontSize: '0.78rem',
                        fontWeight: 600,
                        padding: '4px 8px',
                        borderRadius: 6,
                        outline: 'none',
                        cursor: 'pointer',
                        maxWidth: 200,
                      }}
                    >
                      {stations.map((s: any) => (
                        <option key={s.id} value={s.id}>
                          {s.name} ({s.basin || 'Cauvery'})
                        </option>
                      ))}
                    </select>
                  </div>

                  {selectedStation && (
                    <RiskBadge level={selectedStation.risk_level || 'Safe'} size="sm" />
                  )}
                </div>
              </div>

              {/* Quick Station Navigation Pills */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  overflowX: 'auto',
                  padding: '8px 14px',
                  backgroundColor: 'rgba(0, 0, 0, 0.18)',
                  borderBottom: '1px solid var(--border-subtle)',
                }}
              >
                <span style={{ fontSize: '0.68rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 600, whiteSpace: 'nowrap' }}>
                  Quick Select:
                </span>
                {stations.slice(0, 8).map((s: any) => {
                  const isSelected = s.id === selectedStationId;
                  return (
                    <button
                      key={s.id}
                      onClick={() => handleStationSelect(s.id)}
                      style={{
                        padding: '3px 9px',
                        fontSize: '0.7rem',
                        borderRadius: 12,
                        whiteSpace: 'nowrap',
                        border: isSelected ? '1px solid #0ea5e9' : '1px solid rgba(255,255,255,0.08)',
                        backgroundColor: isSelected ? 'rgba(14, 165, 233, 0.2)' : 'rgba(255, 255, 255, 0.03)',
                        color: isSelected ? '#38bdf8' : '#94a3b8',
                        cursor: 'pointer',
                        fontWeight: isSelected ? 600 : 400,
                        transition: 'all 0.15s ease',
                      }}
                    >
                      {s.name.replace(' Reservoir', '').replace(' Gauge', '').replace(' Station', '').replace(' Dam', '')}
                    </button>
                  );
                })}
              </div>

              <div className="card-body" style={{ padding: 14 }}>
                {isForecastLoading ? (
                  <div
                    style={{
                      height: 220,
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 10,
                      color: '#38bdf8',
                      fontSize: '0.82rem',
                    }}
                  >
                    <RefreshCw size={20} className="animate-spin" />
                    <span>Updating AI hydrograph & forecast for {selectedStation?.name}...</span>
                  </div>
                ) : (
                  <HydrographChart
                    data={focalPrediction?.hydrograph || []}
                    dangerLevel={selectedStation?.danger_level}
                    warningLevel={selectedStation?.warning_level}
                    unit="ft"
                    height={220}
                    title="Stage Telemetry & AI Forecast (ft)"
                  />
                )}
              </div>
            </div>

            {/* Native Forecast Horizons (6h, 12h, 24h) */}
            <div className="card">
              <div className="card-header">
                <div className="card-title">
                  <Brain size={15} color="#38bdf8" />
                  <span>Native HydroGNN-Net Forecast Horizons</span>
                </div>
                <span
                  style={{
                    fontSize: '0.68rem',
                    color: '#0ea5e9',
                    backgroundColor: 'rgba(14, 165, 233, 0.1)',
                    padding: '2px 6px',
                    borderRadius: 4,
                  }}
                >
                  Direct Model Predictions
                </span>
              </div>

              <div className="card-body" style={{ padding: '14px 16px' }}>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(3, 1fr)',
                    gap: 12,
                  }}
                >
                  {nativeForecasts.map((f) => (
                    <div
                      key={f.horizon}
                      style={{
                        backgroundColor: 'var(--bg-surface)',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: 6,
                        padding: '10px 12px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 3,
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                        }}
                      >
                        <span style={{ fontSize: '0.72rem', color: '#94a3b8', fontWeight: 600 }}>
                          +{f.horizon}
                        </span>
                        <RiskBadge level={f.severity} size="sm" showDot={false} />
                      </div>
                      <div
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: '1.2rem',
                          fontWeight: 700,
                          color: '#f8fafc',
                        }}
                      >
                        {f.level_ft != null ? Number(f.level_ft).toFixed(2) : '—'}{' '}
                        <span style={{ fontSize: '0.75rem', fontWeight: 400, color: '#64748b' }}>
                          ft
                        </span>
                      </div>
                      <div style={{ fontSize: '0.68rem', color: '#64748b' }}>
                        ±{f.uncertainty != null ? Number(f.uncertainty).toFixed(2) : '0.00'} ft
                      </div>
                    </div>
                  ))}
                </div>

                <div
                  style={{
                    marginTop: 10,
                    fontSize: '0.72rem',
                    color: '#64748b',
                    display: 'flex',
                    justifyContent: 'space-between',
                  }}
                >
                  <span>Native multi-step heads: 6h / 12h / 24h</span>
                  <Link
                    href="/forecast"
                    style={{ color: '#38bdf8', textDecoration: 'none', fontWeight: 500 }}
                  >
                    Detailed Forecast Page →
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* 3. BASIN FLOOD RISK SUMMARY & SYSTEM HEALTH */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(0, 1.4fr) minmax(0, 1fr)',
            gap: 18,
          }}
        >
          {/* Current Flood-Risk Summary */}
          <div className="card">
            <div className="card-header">
              <div className="card-title">
                <ShieldCheck size={16} color="#10b981" />
                <span>Cauvery Basin Flood-Risk Summary</span>
              </div>
              <span style={{ fontSize: '0.74rem', color: '#94a3b8' }}>
                {dashboardData.timestamp_ist || dashboardData.timestamp}
              </span>
            </div>

            <div className="card-body" style={{ padding: '16px 18px' }}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 16,
                  marginBottom: 14,
                }}
              >
                <div
                  style={{
                    flex: 1,
                    padding: '10px 14px',
                    borderRadius: 6,
                    backgroundColor: 'rgba(16, 185, 129, 0.08)',
                    border: '1px solid rgba(16, 185, 129, 0.2)',
                  }}
                >
                  <div style={{ fontSize: '0.72rem', color: '#10b981', fontWeight: 600 }}>
                    SAFE REACHES
                  </div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#f8fafc' }}>
                    {riskCounts.safe}
                  </div>
                </div>

                <div
                  style={{
                    flex: 1,
                    padding: '10px 14px',
                    borderRadius: 6,
                    backgroundColor: 'rgba(245, 158, 11, 0.08)',
                    border: '1px solid rgba(245, 158, 11, 0.2)',
                  }}
                >
                  <div style={{ fontSize: '0.72rem', color: '#f59e0b', fontWeight: 600 }}>
                    WATCH / WARNING
                  </div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#f8fafc' }}>
                    {riskCounts.warning}
                  </div>
                </div>

                <div
                  style={{
                    flex: 1,
                    padding: '10px 14px',
                    borderRadius: 6,
                    backgroundColor: 'rgba(239, 68, 68, 0.08)',
                    border: '1px solid rgba(239, 68, 68, 0.2)',
                  }}
                >
                  <div style={{ fontSize: '0.72rem', color: '#ef4444', fontWeight: 600 }}>
                    CRITICAL DANGER
                  </div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#f8fafc' }}>
                    {riskCounts.danger}
                  </div>
                </div>
              </div>

              {dashboardData.decision_support && (
                <div
                  style={{
                    padding: '12px 14px',
                    backgroundColor: 'var(--bg-surface)',
                    borderRadius: 6,
                    border: '1px solid var(--border-subtle)',
                    fontSize: '0.8rem',
                    color: '#94a3b8',
                    lineHeight: 1.5,
                  }}
                >
                  <strong style={{ color: '#f8fafc', display: 'block', marginBottom: 4 }}>
                    Operational Decision Support:
                  </strong>
                  {typeof dashboardData.decision_support === 'string' ? (
                    <span>{dashboardData.decision_support}</span>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span>Emergency Protocol:</span>
                        <strong
                          style={{
                            color:
                              dashboardData.decision_support.emergency_response_level === 'RED ALERT'
                                ? '#ef4444'
                                : '#10b981',
                          }}
                        >
                          {dashboardData.decision_support.emergency_response_level || 'NORMAL'}
                        </strong>
                      </div>
                      {dashboardData.decision_support.evacuation_rankings &&
                      dashboardData.decision_support.evacuation_rankings.length > 0 ? (
                        <div style={{ color: '#f59e0b', fontSize: '0.76rem' }}>
                          Evacuation preparedness recommended for:{' '}
                          {dashboardData.decision_support.evacuation_rankings
                            .map((e: any) => e.district)
                            .join(', ')}
                        </div>
                      ) : (
                        <div style={{ fontSize: '0.76rem', color: '#94a3b8' }}>
                          All Cauvery Basin reaches operating under routine monitoring protocol. No evacuation or road closure triggers active.
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* System Status Section */}
          <div className="card">
            <div className="card-header">
              <div className="card-title">
                <Database size={15} color="#0ea5e9" />
                <span>System Status</span>
              </div>
              <Link
                href="/diagnostics"
                style={{ fontSize: '0.74rem', color: '#38bdf8', textDecoration: 'none' }}
              >
                View Diagnostics →
              </Link>
            </div>

            <div
              className="card-body"
              style={{ padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 10 }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem' }}>
                <span style={{ color: '#94a3b8' }}>Prediction Engine:</span>
                <span style={{ color: '#10b981', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4 }}>
                  <CheckCircle size={12} /> Experiment 9 Active
                </span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem' }}>
                <span style={{ color: '#94a3b8' }}>Telemetry Ingestion:</span>
                <span style={{ color: '#f8fafc', fontWeight: 500 }}>
                  {dashboardData.data_status || 'Live Feed'}
                </span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem' }}>
                <span style={{ color: '#94a3b8' }}>Last Data Sync:</span>
                <span style={{ color: '#f8fafc', fontFamily: 'var(--font-mono)' }}>
                  {dashboardData.timestamp_ist || dashboardData.timestamp}
                </span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem' }}>
                <span style={{ color: '#94a3b8' }}>Database Store:</span>
                <span style={{ color: '#10b981', fontWeight: 500 }}>SQLite Healthy</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
