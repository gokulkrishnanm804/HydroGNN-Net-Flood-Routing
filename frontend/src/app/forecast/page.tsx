'use client';
import React, { useState, useEffect, useMemo } from 'react';
import AppLayout from '../AppLayout';
import RiskBadge from '../components/RiskBadge';
import { LoadingSkeleton, ErrorBanner } from '../components/StateViews';
import { api } from '../../services/api';
import {
  Brain,
  Shield,
  Layers,
  Info,
  Clock,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  Droplets,
  AlertTriangle,
  RefreshCw,
  Cpu,
  Compass,
  CheckCircle2,
  Sliders,
  ShieldAlert,
  Gauge,
  Navigation,
} from 'lucide-react';

export default function ForecastPage() {
  const [stations, setStations] = useState<any[]>([]);
  const [selectedStationId, setSelectedStationId] = useState<string>('METTUR');
  const [predictionData, setPredictionData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [hasError, setHasError] = useState<boolean>(false);

  const loadInitialData = async () => {
    try {
      setIsLoading(true);
      setHasError(false);
      await api.login();
      const dash = await api.getDashboard();
      const uniqueStations = Array.from(
        new Map((dash.stations || []).map((s: any) => [s.id, s])).values()
      );
      setStations(uniqueStations);

      if (uniqueStations.length > 0) {
        const initial = uniqueStations.some((s: any) => s.id === 'METTUR')
          ? 'METTUR'
          : uniqueStations[0]?.id;
        setSelectedStationId(initial);

        const pred = await api.getPrediction(initial, [1, 3, 6, 12, 18, 24]);
        setPredictionData(pred);
      }
    } catch (err) {
      console.error('Failed to load forecast data:', err);
      setHasError(true);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadInitialData();
  }, []);

  const handleStationChange = async (stationId: string) => {
    try {
      setIsRefreshing(true);
      setSelectedStationId(stationId);
      const pred = await api.getPrediction(stationId, [1, 3, 6, 12, 18, 24]);
      setPredictionData(pred);
    } catch (err) {
      console.error(`Failed to fetch forecast for station ${stationId}:`, err);
    } finally {
      setIsRefreshing(false);
    }
  };

  const selectedStation = useMemo(() => {
    return stations.find((s: any) => s.id === selectedStationId) || stations[0] || null;
  }, [stations, selectedStationId]);

  const currentObservedLevel = useMemo(() => {
    if (!predictionData?.hydrograph) return Number(selectedStation?.water_level || 0);
    const obs = predictionData.hydrograph.filter((p: any) => p.observed != null);
    if (obs.length > 0) {
      return Number(obs[obs.length - 1].observed);
    }
    return Number(selectedStation?.water_level || 0);
  }, [predictionData, selectedStation]);

  const dangerLevel = useMemo(() => {
    return Number(selectedStation?.danger_level || predictionData?.danger_level_m || 393.7);
  }, [selectedStation, predictionData]);

  const warningLevel = useMemo(() => {
    return Number(selectedStation?.warning_level || predictionData?.warning_level_m || dangerLevel * 0.8);
  }, [selectedStation, predictionData, dangerLevel]);

  // Clearance Headroom
  const currentClearance = useMemo(() => {
    return Math.max(0, dangerLevel - currentObservedLevel);
  }, [dangerLevel, currentObservedLevel]);

  // Extract native 6h, 12h, 24h predictions
  const nativePredictions = useMemo(() => {
    if (!predictionData?.predictions) return [];
    return [6, 12, 24].map((h) => {
      const p = predictionData.predictions.find((item: any) => item.horizon_hours === h);
      const lvl = p ? p.level_m : null;
      const delta = lvl != null && currentObservedLevel != null ? lvl - currentObservedLevel : null;
      const clearance = lvl != null ? Math.max(0, dangerLevel - lvl) : null;
      return {
        horizon: h,
        level_ft: lvl,
        level_m: lvl != null ? lvl / 3.28084 : null,
        delta_ft: delta,
        uncertainty_ft: p ? p.uncertainty_m : null,
        flood_probability: p ? p.flood_probability : 0,
        severity: p ? p.severity : 'Safe',
        confidence: p ? p.confidence : 0.95,
        clearance_ft: clearance,
      };
    });
  }, [predictionData, currentObservedLevel, dangerLevel]);

  // All 6 horizons detailed trajectory
  const detailedSchedule = useMemo(() => {
    if (!predictionData?.predictions) return [];
    const horizons = [1, 3, 6, 12, 18, 24];
    return horizons.map((h) => {
      const p = predictionData.predictions.find((item: any) => item.horizon_hours === h);
      const lvl = p ? Number(p.level_m) : currentObservedLevel;
      const delta = lvl - currentObservedLevel;
      const unc = p ? Number(p.uncertainty_m) : 0.5;
      const lower = Math.max(0.1, lvl - unc);
      const upper = lvl + unc;
      const clearance = Math.max(0, dangerLevel - lvl);
      const isNative = [6, 12, 24].includes(h);

      // Estimated future time
      const date = new Date();
      date.setHours(date.getHours() + h);
      const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
      const dayStr = date.toLocaleDateString([], { month: 'short', day: 'numeric' });

      // Action Protocol
      let advisory = 'Normal Baseflow — Routine Monitoring';
      if (lvl >= dangerLevel) {
        advisory = 'Emergency: Stage Exceeds Danger Mark — Initiate Evacuation Protocol';
      } else if (lvl >= warningLevel) {
        advisory = 'Warning: Approaching Critical Stage — Sluice Gates on Alert';
      } else if (delta > 1.5) {
        advisory = 'Rising Trajectory: Downstream Watch in Effect';
      }

      return {
        horizon: h,
        isNative,
        timeStr: `${dayStr}, ${timeStr}`,
        level_ft: lvl,
        level_m: lvl / 3.28084,
        delta_ft: delta,
        uncertainty_ft: unc,
        lower_ft: lower,
        upper_ft: upper,
        clearance_ft: clearance,
        flood_prob_pct: Math.round((p?.flood_probability || (lvl / dangerLevel)) * 100),
        severity: p?.severity || (lvl >= dangerLevel ? 'High Risk' : 'Safe'),
        confidence: Math.round((p?.confidence || 0.95) * 100),
        advisory,
      };
    });
  }, [predictionData, currentObservedLevel, dangerLevel, warningLevel]);

  if (isLoading) {
    return (
      <AppLayout>
        <LoadingSkeleton rows={5} height={100} />
      </AppLayout>
    );
  }

  if (hasError || !selectedStation) {
    return (
      <AppLayout>
        <ErrorBanner onRetry={loadInitialData} />
      </AppLayout>
    );
  }

  const meta = predictionData?.routing_metadata || {};

  return (
    <AppLayout>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
        {/* Top Control Header: Station Selector & Real-Time Context */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 16,
            padding: '18px 22px',
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 8,
          }}
        >
          {/* Station Selection Dropdown */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div>
              <span style={{ fontSize: '0.72rem', color: '#94a3b8', textTransform: 'uppercase', display: 'block', fontWeight: 600 }}>
                Forecast Station
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 4 }}>
                <select
                  value={selectedStationId}
                  onChange={(e) => handleStationChange(e.target.value)}
                  style={{
                    backgroundColor: 'var(--bg-surface)',
                    border: '1px solid var(--border-medium)',
                    color: '#f8fafc',
                    fontSize: '0.9rem',
                    fontWeight: 600,
                    padding: '8px 14px',
                    borderRadius: 6,
                    outline: 'none',
                    cursor: 'pointer',
                  }}
                >
                  {stations.map((s: any) => (
                    <option key={s.id} value={s.id}>
                      {s.name} ({s.basin || 'Cauvery'})
                    </option>
                  ))}
                </select>

                <button
                  type="button"
                  onClick={() => handleStationChange(selectedStationId)}
                  disabled={isRefreshing}
                  className="btn btn-sm btn-secondary"
                  title="Re-run GNN Inference for this station"
                  style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '7px 12px' }}
                >
                  <RefreshCw size={13} className={isRefreshing ? 'spin' : ''} />
                  <span>{isRefreshing ? 'Running...' : 'Re-infer'}</span>
                </button>
              </div>
            </div>
          </div>

          {/* Real-time Observed Stage Telemetry & Headroom */}
          <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 20 }}>
            <div>
              <span style={{ fontSize: '0.7rem', color: '#94a3b8', textTransform: 'uppercase', display: 'block' }}>
                Current Observed Stage
              </span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '1.35rem', fontWeight: 700, color: '#f8fafc' }}>
                {currentObservedLevel.toFixed(2)}{' '}
                <span style={{ fontSize: '0.8rem', fontWeight: 400, color: '#94a3b8' }}>ft</span>
              </span>
            </div>

            <div style={{ borderLeft: '1px solid var(--border-subtle)', paddingLeft: 16 }}>
              <span style={{ fontSize: '0.7rem', color: '#94a3b8', textTransform: 'uppercase', display: 'block' }}>
                Warning / Danger
              </span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '1rem', fontWeight: 600, color: '#e2e8f0' }}>
                <span style={{ color: '#f59e0b' }}>{warningLevel.toFixed(1)}</span> /{' '}
                <span style={{ color: '#ef4444' }}>{dangerLevel.toFixed(1)}</span>{' '}
                <span style={{ fontSize: '0.75rem', color: '#64748b' }}>ft</span>
              </span>
            </div>

            <div style={{ borderLeft: '1px solid var(--border-subtle)', paddingLeft: 16 }}>
              <span style={{ fontSize: '0.7rem', color: '#94a3b8', textTransform: 'uppercase', display: 'block' }}>
                Clearance Headroom
              </span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '1.15rem', fontWeight: 700, color: '#10b981' }}>
                {currentClearance.toFixed(2)}{' '}
                <span style={{ fontSize: '0.75rem', fontWeight: 400, color: '#6ee7b7' }}>ft to danger</span>
              </span>
            </div>

            <div style={{ borderLeft: '1px solid var(--border-subtle)', paddingLeft: 16 }}>
              <span style={{ fontSize: '0.7rem', color: '#94a3b8', textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>
                Current Risk
              </span>
              <RiskBadge level={selectedStation.risk_level || 'Safe'} />
            </div>
          </div>
        </div>

        {/* 3 Native GNN Forecast Cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
          {nativePredictions.map((pred) => (
            <div
              key={pred.horizon}
              className="card"
              style={{
                padding: '18px 20px',
                position: 'relative',
                overflow: 'hidden',
                borderLeft: '4px solid #0ea5e9',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 10,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Brain size={15} color="#0ea5e9" />
                  <span style={{ fontSize: '0.82rem', fontWeight: 700, color: '#38bdf8' }}>
                    +{pred.horizon}h Forecast Horizon
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  {pred.delta_ft != null && (
                    <span
                      style={{
                        fontSize: '0.72rem',
                        fontWeight: 600,
                        color: pred.delta_ft >= 0 ? '#38bdf8' : '#10b981',
                        backgroundColor: pred.delta_ft >= 0 ? 'rgba(56, 189, 248, 0.12)' : 'rgba(16, 185, 129, 0.12)',
                        border: `1px solid ${pred.delta_ft >= 0 ? 'rgba(56, 189, 248, 0.3)' : 'rgba(16, 185, 129, 0.3)'}`,
                        borderRadius: 4,
                        padding: '2px 7px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 2,
                      }}
                    >
                      {pred.delta_ft >= 0 ? (
                        <>
                          <ArrowUpRight size={12} /> +{pred.delta_ft.toFixed(2)} ft
                        </>
                      ) : (
                        <>
                          <ArrowDownRight size={12} /> {pred.delta_ft.toFixed(2)} ft
                        </>
                      )}
                    </span>
                  )}
                  <span
                    style={{
                      fontSize: '0.64rem',
                      color: '#10b981',
                      backgroundColor: 'rgba(16, 185, 129, 0.12)',
                      border: '1px solid rgba(16, 185, 129, 0.3)',
                      borderRadius: 4,
                      padding: '2px 6px',
                      fontWeight: 700,
                      textTransform: 'uppercase',
                    }}
                  >
                    Native GNN Head
                  </span>
                </div>
              </div>

              {/* Main Predicted Number */}
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '2rem',
                    fontWeight: 700,
                    color: '#f8fafc',
                    lineHeight: 1.1,
                  }}
                >
                  {pred.level_ft != null ? Number(pred.level_ft).toFixed(2) : '—'}
                </span>
                <span style={{ fontSize: '0.9rem', color: '#94a3b8' }}>ft</span>
                {pred.level_m != null && (
                  <span style={{ fontSize: '0.8rem', color: '#64748b', marginLeft: 4 }}>
                    ({pred.level_m.toFixed(2)} m)
                  </span>
                )}
              </div>

              {/* 95% Confidence Interval & Uncertainty Range */}
              <div
                style={{
                  marginTop: 12,
                  padding: '8px 10px',
                  backgroundColor: 'rgba(0, 0, 0, 0.25)',
                  borderRadius: 6,
                  border: '1px solid var(--border-subtle)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  fontSize: '0.74rem',
                }}
              >
                <span style={{ color: '#94a3b8' }}>
                  95% Confidence Band:
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', color: '#e2e8f0', fontWeight: 600 }}>
                  ±{pred.uncertainty_ft != null ? Number(pred.uncertainty_ft).toFixed(2) : '0.00'} ft
                </span>
              </div>

              {/* Footer: Clearance Headroom & Severity */}
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginTop: 12,
                  fontSize: '0.74rem',
                }}
              >
                <span style={{ color: '#94a3b8' }}>
                  Remaining Headroom:{' '}
                  <strong style={{ color: '#38bdf8', fontFamily: 'var(--font-mono)' }}>
                    {pred.clearance_ft != null ? pred.clearance_ft.toFixed(2) : '—'} ft
                  </strong>
                </span>
                <RiskBadge level={pred.severity} size="sm" />
              </div>
            </div>
          ))}
        </div>

        {/* SECTION 1: DETAILED MULTI-HORIZON INUNDATION SCHEDULE TABLE */}
        <div className="card" style={{ padding: '20px 22px' }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: 12,
              marginBottom: 16,
            }}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Clock size={16} color="#0ea5e9" />
                <h3 style={{ fontSize: '1.05rem', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
                  {selectedStation.name} — Multi-Horizon Inundation & Trajectory Schedule
                </h3>
              </div>
              <p style={{ fontSize: '0.76rem', color: '#94a3b8', margin: '4px 0 0' }}>
                Continuous forward projections across 6 horizons generated by HydroGNN-Net Exp 9 neural heads & shape-preserving PCHIP interpolation
              </p>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.72rem', color: '#64748b' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: '#10b981', display: 'inline-block' }} />
                Native GNN Heads (6h, 12h, 24h)
              </span>
              <span>·</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: '#0ea5e9', display: 'inline-block' }} />
                PCHIP Spline (1h, 3h, 18h)
              </span>
            </div>
          </div>

          <div className="table-container" style={{ border: 'none', borderRadius: 6, overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Horizon Step</th>
                  <th>Target Time</th>
                  <th>Projected Stage</th>
                  <th>Stage Delta</th>
                  <th>95% Confidence Band</th>
                  <th>Clearance to Danger</th>
                  <th>Inundation Prob</th>
                  <th>Risk Status</th>
                  <th>Operational Action Advisory</th>
                </tr>
              </thead>
              <tbody>
                {detailedSchedule.map((row) => (
                  <tr key={row.horizon}>
                    {/* Horizon Step */}
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span
                          style={{
                            fontWeight: 700,
                            color: row.isNative ? '#38bdf8' : '#cbd5e1',
                            fontFamily: 'var(--font-mono)',
                          }}
                        >
                          +{row.horizon}h
                        </span>
                        <span
                          style={{
                            fontSize: '0.62rem',
                            padding: '1px 5px',
                            borderRadius: 3,
                            fontWeight: 600,
                            textTransform: 'uppercase',
                            backgroundColor: row.isNative ? 'rgba(16, 185, 129, 0.15)' : 'rgba(14, 165, 233, 0.12)',
                            color: row.isNative ? '#34d399' : '#38bdf8',
                            border: `1px solid ${row.isNative ? 'rgba(16, 185, 129, 0.3)' : 'rgba(14, 165, 233, 0.3)'}`,
                          }}
                        >
                          {row.isNative ? 'Native' : 'Spline'}
                        </span>
                      </div>
                    </td>

                    {/* Target Time */}
                    <td style={{ color: '#94a3b8', fontSize: '0.78rem' }}>
                      {row.timeStr}
                    </td>

                    {/* Projected Stage */}
                    <td>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
                        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: '#f8fafc', fontSize: '0.92rem' }}>
                          {row.level_ft.toFixed(2)} ft
                        </span>
                        <span style={{ fontSize: '0.7rem', color: '#64748b' }}>
                          ({row.level_m.toFixed(2)} m)
                        </span>
                      </div>
                    </td>

                    {/* Stage Delta */}
                    <td>
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontWeight: 600,
                          fontSize: '0.78rem',
                          color: row.delta_ft > 0 ? '#38bdf8' : row.delta_ft < 0 ? '#10b981' : '#64748b',
                          display: 'flex',
                          alignItems: 'center',
                          gap: 3,
                        }}
                      >
                        {row.delta_ft > 0 ? (
                          <>
                            <ArrowUpRight size={13} /> +{row.delta_ft.toFixed(2)} ft
                          </>
                        ) : row.delta_ft < 0 ? (
                          <>
                            <ArrowDownRight size={13} /> {row.delta_ft.toFixed(2)} ft
                          </>
                        ) : (
                          <>
                            <Minus size={13} /> 0.00 ft
                          </>
                        )}
                      </span>
                    </td>

                    {/* 95% Confidence Band */}
                    <td>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.76rem', color: '#cbd5e1' }}>
                        [{row.lower_ft.toFixed(2)} – {row.upper_ft.toFixed(2)} ft]
                        <span style={{ color: '#64748b', marginLeft: 4 }}>
                          (±{row.uncertainty_ft.toFixed(2)})
                        </span>
                      </div>
                    </td>

                    {/* Clearance to Danger */}
                    <td>
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontWeight: 600,
                          fontSize: '0.78rem',
                          color: row.clearance_ft < 50 ? '#ef4444' : row.clearance_ft < 100 ? '#f59e0b' : '#10b981',
                        }}
                      >
                        {row.clearance_ft.toFixed(2)} ft
                      </span>
                    </td>

                    {/* Inundation Probability */}
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div
                          style={{
                            flex: 1,
                            minWidth: 45,
                            height: 6,
                            backgroundColor: 'rgba(255, 255, 255, 0.08)',
                            borderRadius: 3,
                            overflow: 'hidden',
                          }}
                        >
                          <div
                            style={{
                              width: `${Math.min(100, Math.max(0, row.flood_prob_pct))}%`,
                              height: '100%',
                              backgroundColor:
                                row.flood_prob_pct > 75
                                  ? '#ef4444'
                                  : row.flood_prob_pct > 40
                                  ? '#f59e0b'
                                  : '#10b981',
                              borderRadius: 3,
                            }}
                          />
                        </div>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: '#94a3b8' }}>
                          {row.flood_prob_pct}%
                        </span>
                      </div>
                    </td>

                    {/* Risk Status */}
                    <td>
                      <RiskBadge level={row.severity} size="sm" />
                    </td>

                    {/* Operational Advisory */}
                    <td style={{ fontSize: '0.75rem', color: '#e2e8f0', maxWidth: 260 }}>
                      {row.advisory}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* SECTION 2: BASIN-WIDE RIVER ROUTING CASCADE & VULNERABILITY MATRIX */}
        <div className="card" style={{ padding: '20px 22px' }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: 12,
              marginBottom: 16,
            }}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Navigation size={16} color="#0ea5e9" />
                <h3 style={{ fontSize: '1.05rem', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
                  Basin-Wide River Routing Cascade & Vulnerability Matrix
                </h3>
              </div>
              <p style={{ fontSize: '0.76rem', color: '#94a3b8', margin: '4px 0 0' }}>
                Key hydrological routing nodes along the Cauvery main stem, Bhavani, Amaravathi, and Vaigai reaches
              </p>
            </div>
            <span style={{ fontSize: '0.74rem', color: '#64748b' }}>
              Click &quot;Inspect Forecast&quot; to change the active analysis station
            </span>
          </div>

          <div className="table-container" style={{ border: 'none', borderRadius: 6, overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Station Name</th>
                  <th>River Reach</th>
                  <th>Current Level</th>
                  <th>Danger Mark</th>
                  <th>Capacity Utilization</th>
                  <th>24h Rainfall</th>
                  <th>Soil Saturation</th>
                  <th>Current Status</th>
                  <th>Quick Action</th>
                </tr>
              </thead>
              <tbody>
                {stations.slice(0, 10).map((s: any) => {
                  const isSelected = s.id === selectedStationId;
                  const ratioPct = Math.min(100, Math.round(((s.water_level || 0) / (s.danger_level || 1)) * 100));
                  return (
                    <tr
                      key={s.id}
                      onClick={() => handleStationChange(s.id)}
                      style={{
                        cursor: 'pointer',
                        backgroundColor: isSelected ? 'rgba(14, 165, 233, 0.12)' : undefined,
                      }}
                    >
                      <td style={{ fontWeight: 600, color: isSelected ? '#38bdf8' : '#f8fafc' }}>
                        {s.name}
                      </td>
                      <td style={{ color: '#94a3b8' }}>{s.basin || 'Cauvery'}</td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                        {Number(s.water_level || 0).toFixed(2)} ft
                      </td>
                      <td style={{ fontFamily: 'var(--font-mono)', color: '#ef4444' }}>
                        {Number(s.danger_level || 0).toFixed(1)} ft
                      </td>
                      <td style={{ minWidth: 120 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <div
                            style={{
                              flex: 1,
                              height: 6,
                              backgroundColor: 'rgba(255, 255, 255, 0.08)',
                              borderRadius: 3,
                              overflow: 'hidden',
                            }}
                          >
                            <div
                              style={{
                                width: `${ratioPct}%`,
                                height: '100%',
                                backgroundColor: ratioPct > 85 ? '#ef4444' : ratioPct > 60 ? '#f59e0b' : '#10b981',
                                borderRadius: 3,
                              }}
                            />
                          </div>
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: '#94a3b8' }}>
                            {ratioPct}%
                          </span>
                        </div>
                      </td>
                      <td style={{ fontFamily: 'var(--font-mono)', color: '#94a3b8' }}>
                        {Number(s.rain_observed || 0).toFixed(1)} mm
                      </td>
                      <td style={{ fontFamily: 'var(--font-mono)', color: '#94a3b8' }}>
                        {s.soil_moisture ? `${Math.round(s.soil_moisture * 100)}%` : '45%'}
                      </td>
                      <td>
                        <RiskBadge level={s.risk_level || 'Safe'} size="sm" />
                      </td>
                      <td>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleStationChange(s.id);
                          }}
                          className={`btn btn-sm ${isSelected ? 'btn-primary' : 'btn-secondary'}`}
                          style={{ fontSize: '0.68rem', padding: '3px 8px', whiteSpace: 'nowrap' }}
                        >
                          {isSelected ? 'Active' : 'Inspect Forecast →'}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* SECTION 3: HYDROLOGICAL FACTORS & GNN PHYSICS DIAGNOSTICS (GRID OF 4 CARDS) */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
          {/* Card 1: 24h Antecedent Rain */}
          <div className="card" style={{ padding: '16px 18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#38bdf8', marginBottom: 8 }}>
              <Droplets size={16} />
              <span style={{ fontSize: '0.78rem', fontWeight: 600, textTransform: 'uppercase' }}>
                24h Antecedent Rain
              </span>
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.6rem', fontWeight: 700, color: '#f8fafc' }}>
              {meta.rain_24h_mm != null ? meta.rain_24h_mm : Number(selectedStation.rain_observed || 0).toFixed(1)}{' '}
              <span style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: 400 }}>mm</span>
            </div>
            <p style={{ fontSize: '0.72rem', color: '#94a3b8', margin: '6px 0 0' }}>
              Cumulative basin gauge precipitation feeding direct surface runoff
            </p>
          </div>

          {/* Card 2: Soil Moisture Saturation */}
          <div className="card" style={{ padding: '16px 18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#10b981', marginBottom: 8 }}>
              <Compass size={16} />
              <span style={{ fontSize: '0.78rem', fontWeight: 600, textTransform: 'uppercase' }}>
                Soil Saturation Proxy
              </span>
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.6rem', fontWeight: 700, color: '#f8fafc' }}>
              {meta.soil_moisture != null ? Math.round(meta.soil_moisture * 100) : 45}%
            </div>
            <p style={{ fontSize: '0.72rem', color: '#94a3b8', margin: '6px 0 0' }}>
              CN-based catchment retention index governing infiltration excess
            </p>
          </div>

          {/* Card 3: Neural Model Architecture */}
          <div className="card" style={{ padding: '16px 18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#a855f7', marginBottom: 8 }}>
              <Cpu size={16} />
              <span style={{ fontSize: '0.78rem', fontWeight: 600, textTransform: 'uppercase' }}>
                Inference Architecture
              </span>
            </div>
            <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#f8fafc', lineHeight: 1.3 }}>
              HydroGNN-Net Exp 9
            </div>
            <p style={{ fontSize: '0.72rem', color: '#94a3b8', margin: '6px 0 0' }}>
              GRU + GATv2 + GraphSAGE with Trend-Conditioned Residual Gating
            </p>
          </div>

          {/* Card 4: Routing Law */}
          <div className="card" style={{ padding: '16px 18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#f59e0b', marginBottom: 8 }}>
              <Gauge size={16} />
              <span style={{ fontSize: '0.78rem', fontWeight: 600, textTransform: 'uppercase' }}>
                Hydrological Routing
              </span>
            </div>
            <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#f8fafc', lineHeight: 1.3 }}>
              Nash-Sutcliffe IUH
            </div>
            <p style={{ fontSize: '0.72rem', color: '#94a3b8', margin: '6px 0 0' }}>
              Conservation of volume with PCHIP C1-continuous spline interpolation
            </p>
          </div>
        </div>

        {/* SECTION 4: OPERATIONAL EARLY WARNING ACTION PROTOCOL */}
        <div
          style={{
            padding: '16px 20px',
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 8,
            display: 'flex',
            alignItems: 'flex-start',
            gap: 14,
          }}
        >
          <ShieldAlert size={20} color="#0ea5e9" style={{ flexShrink: 0, marginTop: 2 }} />
          <div style={{ fontSize: '0.78rem', color: '#cbd5e1', lineHeight: 1.5 }}>
            <strong style={{ color: '#f8fafc', display: 'block', marginBottom: 4 }}>
              Operational Early Warning & Decision Support Protocol:
            </strong>
            When projected water stage approaches within 10% of Warning Level ({warningLevel.toFixed(1)} ft), river wardens are automatically alerted via the automated notification queue. If 24h trajectory forecasts breach Danger Level ({dangerLevel.toFixed(1)} ft), emergency sluice gate regulation protocols are initiated at upstream dams (Mettur / Bhavanisagar / Amaravathi).
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
