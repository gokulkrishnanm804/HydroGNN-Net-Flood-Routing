'use client';
import React, { useState, useEffect, useMemo } from 'react';
import AppLayout from '../AppLayout';
import RiskBadge from '../components/RiskBadge';
import StationObservedChart from '../components/StationObservedChart';
import { LoadingSkeleton, ErrorBanner } from '../components/StateViews';
import { api } from '../../services/api';
import Link from 'next/link';
import {
  Radio,
  TrendingUp,
  MapPin,
  CloudRain,
  Droplets,
  Layers,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  Activity,
  Gauge,
  Cpu,
  ExternalLink,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';

export default function StationsPage() {
  const [stations, setStations] = useState<any[]>([]);
  const [selectedStationId, setSelectedStationId] = useState<string>('METTUR');
  const [predictionData, setPredictionData] = useState<any>(null);
  const [isTelemetryLoading, setIsTelemetryLoading] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [hasError, setHasError] = useState<boolean>(false);
  const [filterRisk, setFilterRisk] = useState<string>('all');
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(8);

  const fetchStations = async () => {
    try {
      setIsLoading(true);
      setHasError(false);
      await api.login();
      const dash = await api.getDashboard();
      const stationsList = dash.stations || [];
      setStations(stationsList);

      if (stationsList.length > 0) {
        const initial = stationsList.some((s: any) => s.id === 'METTUR')
          ? 'METTUR'
          : stationsList[0]?.id;
        setSelectedStationId(initial);

        const pred = await api.getPrediction(initial, [6, 12, 24]);
        setPredictionData(pred);
      }
    } catch (err) {
      console.error('Failed to load stations:', err);
      setHasError(true);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchStations();
  }, []);

  const handleSelectStation = async (stationId: string) => {
    if (!stationId) return;
    try {
      setSelectedStationId(stationId);
      // Auto-jump to page containing selected station
      const idx = filteredStations.findIndex((s: any) => s.id === stationId);
      if (idx >= 0) {
        const targetPage = Math.floor(idx / pageSize) + 1;
        setCurrentPage(targetPage);
      }
      setIsTelemetryLoading(true);
      const pred = await api.getPrediction(stationId, [6, 12, 24]);
      setPredictionData(pred);
    } catch (err) {
      console.error(`Failed to load telemetry for station ${stationId}:`, err);
    } finally {
      setIsTelemetryLoading(false);
    }
  };

  const selectedStation = useMemo(() => {
    return stations.find((s: any) => s.id === selectedStationId) || stations[0] || null;
  }, [stations, selectedStationId]);

  // Filter stations based on risk
  const filteredStations = useMemo(() => {
    if (filterRisk === 'all') return stations;
    return stations.filter((s: any) => {
      const risk = (s.risk_level || '').toLowerCase();
      if (filterRisk === 'attention') {
        return (
          risk.includes('warn') ||
          risk.includes('danger') ||
          risk.includes('severe') ||
          risk.includes('high')
        );
      }
      return risk.includes(filterRisk);
    });
  }, [stations, filterRisk]);

  // Reset page when filter changes
  useEffect(() => {
    setCurrentPage(1);
  }, [filterRisk]);

  // Pagination calculations
  const totalPages = Math.max(1, Math.ceil(filteredStations.length / pageSize));

  const paginatedStations = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filteredStations.slice(start, start + pageSize);
  }, [filteredStations, currentPage, pageSize]);

  // Hydraulic threshold clearance calculations
  const clearanceToDanger = useMemo(() => {
    if (!selectedStation?.danger_level || !selectedStation?.water_level) return null;
    return Number(selectedStation.danger_level) - Number(selectedStation.water_level);
  }, [selectedStation]);

  const capacityRatio = useMemo(() => {
    if (!selectedStation?.danger_level || !selectedStation?.water_level) return 0;
    const ratio = (Number(selectedStation.water_level) / Number(selectedStation.danger_level)) * 100;
    return Math.min(100, Math.max(0, ratio));
  }, [selectedStation]);

  if (isLoading) {
    return (
      <AppLayout>
        <LoadingSkeleton rows={6} height={80} />
      </AppLayout>
    );
  }

  if (hasError || stations.length === 0) {
    return (
      <AppLayout>
        <ErrorBanner onRetry={fetchStations} />
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        {/* Top Header & Filters */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <h2 style={{ fontSize: '1.2rem', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
              Cauvery Basin River Stations
            </h2>
            <p style={{ fontSize: '0.8rem', color: '#94a3b8', margin: '2px 0 0' }}>
              Monitoring 8 active hydrological gauges along the Cauvery main stem and tributaries
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: '0.74rem', color: '#94a3b8' }}>Filter:</span>
            {['all', 'attention', 'safe'].map((opt) => (
              <button
                key={opt}
                onClick={() => setFilterRisk(opt)}
                className={`btn btn-sm ${filterRisk === opt ? 'btn-primary' : 'btn-secondary'}`}
                style={{ textTransform: 'capitalize' }}
              >
                {opt === 'attention' ? 'Needs Attention' : opt}
              </button>
            ))}
          </div>
        </div>

        {/* 2-Column Layout: Stations Table (Left) + Detail Panel (Right) */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(0, 1.25fr) minmax(0, 1fr)',
            gap: 20,
          }}
        >
          {/* LEFT: Clean Stations Table */}
          <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
            <div className="card-header">
              <div className="card-title">
                <Radio size={15} color="#0ea5e9" />
                <span>Monitored River Stations ({filteredStations.length})</span>
              </div>
              <span style={{ fontSize: '0.72rem', color: '#64748b' }}>
                Select a row to inspect
              </span>
            </div>

            <div className="table-container" style={{ border: 'none', borderRadius: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Station Name</th>
                    <th>River Reach</th>
                    <th>Current Level</th>
                    <th>Danger Level</th>
                    <th>Risk Status</th>
                    <th>24h Rain</th>
                    <th>Trend</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedStations.map((s: any) => {
                    const isSelected = s.id === selectedStationId;
                    const pctOfDanger = (s.water_level / (s.danger_level || 1)) * 100;
                    const isRising = pctOfDanger > 70;
                    const isFalling = pctOfDanger < 30;

                    return (
                      <tr
                        key={s.id}
                        onClick={() => handleSelectStation(s.id)}
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
                        <td>
                          <RiskBadge level={s.risk_level || 'Safe'} size="sm" />
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', color: '#94a3b8' }}>
                          {Number(s.rain_observed || 0).toFixed(1)} mm
                        </td>
                        <td>
                          {isRising ? (
                            <span style={{ color: '#f59e0b', display: 'flex', alignItems: 'center', gap: 2 }}>
                              <ArrowUpRight size={13} /> Rising
                            </span>
                          ) : isFalling ? (
                            <span style={{ color: '#10b981', display: 'flex', alignItems: 'center', gap: 2 }}>
                              <ArrowDownRight size={13} /> Falling
                            </span>
                          ) : (
                            <span style={{ color: '#64748b', display: 'flex', alignItems: 'center', gap: 2 }}>
                              <Minus size={13} /> Steady
                            </span>
                          )}
                        </td>
                        <td>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleSelectStation(s.id);
                            }}
                            className={`btn btn-sm ${isSelected ? 'btn-primary' : 'btn-secondary'}`}
                            style={{
                              fontSize: '0.68rem',
                              padding: '2px 8px',
                              whiteSpace: 'nowrap',
                              cursor: 'pointer',
                            }}
                          >
                            {isSelected ? 'Inspecting' : 'Inspect →'}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Table Pagination Bar */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: 12,
                padding: '12px 16px',
                borderTop: '1px solid var(--border-subtle)',
                backgroundColor: 'rgba(0, 0, 0, 0.15)',
                fontSize: '0.74rem',
              }}
            >
              {/* Left: Summary & Page Size */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, color: '#94a3b8' }}>
                <span>
                  Showing{' '}
                  <strong style={{ color: '#f8fafc' }}>
                    {filteredStations.length > 0 ? (currentPage - 1) * pageSize + 1 : 0}
                  </strong>{' '}
                  –{' '}
                  <strong style={{ color: '#f8fafc' }}>
                    {Math.min(currentPage * pageSize, filteredStations.length)}
                  </strong>{' '}
                  of <strong style={{ color: '#f8fafc' }}>{filteredStations.length}</strong> stations
                </span>

                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <label htmlFor="station-page-size" style={{ color: '#64748b', fontSize: '0.72rem' }}>
                    Rows:
                  </label>
                  <select
                    id="station-page-size"
                    value={pageSize}
                    onChange={(e) => {
                      setPageSize(Number(e.target.value));
                      setCurrentPage(1);
                    }}
                    style={{
                      backgroundColor: 'var(--bg-surface)',
                      border: '1px solid var(--border-medium)',
                      color: '#f8fafc',
                      fontSize: '0.72rem',
                      padding: '2px 6px',
                      borderRadius: 4,
                      outline: 'none',
                      cursor: 'pointer',
                    }}
                  >
                    <option value={6}>6</option>
                    <option value={8}>8</option>
                    <option value={12}>12</option>
                    <option value={25}>All (25)</option>
                  </select>
                </div>
              </div>

              {/* Right: Page Navigation Buttons */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <button
                  type="button"
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="btn btn-sm btn-secondary"
                  style={{
                    padding: '3px 8px',
                    fontSize: '0.72rem',
                    opacity: currentPage === 1 ? 0.4 : 1,
                    cursor: currentPage === 1 ? 'not-allowed' : 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 3,
                  }}
                >
                  <ChevronLeft size={13} />
                  <span>Prev</span>
                </button>

                {Array.from({ length: totalPages }, (_, idx) => idx + 1).map((pg) => {
                  const isActive = pg === currentPage;
                  return (
                    <button
                      key={pg}
                      type="button"
                      onClick={() => setCurrentPage(pg)}
                      className={`btn btn-sm ${isActive ? 'btn-primary' : 'btn-secondary'}`}
                      style={{
                        minWidth: 26,
                        height: 26,
                        padding: '0 6px',
                        fontSize: '0.72rem',
                        fontWeight: isActive ? 700 : 500,
                        cursor: 'pointer',
                        borderRadius: 4,
                      }}
                    >
                      {pg}
                    </button>
                  );
                })}

                <button
                  type="button"
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="btn btn-sm btn-secondary"
                  style={{
                    padding: '3px 8px',
                    fontSize: '0.72rem',
                    opacity: currentPage === totalPages ? 0.4 : 1,
                    cursor: currentPage === totalPages ? 'not-allowed' : 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 3,
                  }}
                >
                  <span>Next</span>
                  <ChevronRight size={13} />
                </button>
              </div>
            </div>
          </div>

          {/* RIGHT: Selected Station Detail Panel */}
          {selectedStation && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {/* Station Identity & Summary */}
              <div className="card">
                <div className="card-header" style={{ flexWrap: 'wrap', gap: 10 }}>
                  <div>
                    <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <MapPin size={16} color="#0ea5e9" />
                      <span>{selectedStation.name}</span>
                    </div>
                    <div style={{ fontSize: '0.74rem', color: '#94a3b8', marginTop: 2 }}>
                      Reach: {selectedStation.basin || 'Cauvery'} River · Coordinates:{' '}
                      <span className="font-mono">
                        {Number(selectedStation.lat || 0).toFixed(3)}°N,{' '}
                        {Number(selectedStation.lon || 0).toFixed(3)}°E
                      </span>
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ fontSize: '0.72rem', color: '#94a3b8', fontWeight: 500 }}>
                        Switch Station:
                      </span>
                      <select
                        id="station-panel-select"
                        value={selectedStationId}
                        onChange={(e) => handleSelectStation(e.target.value)}
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

                    <RiskBadge level={selectedStation.risk_level || 'Safe'} />
                  </div>
                </div>

                <div className="card-body" style={{ padding: '14px 18px' }}>
                  {/* Key Station Metrics Row */}
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(3, 1fr)',
                      gap: 12,
                      marginBottom: 16,
                    }}
                  >
                    <div style={{ backgroundColor: 'var(--bg-surface)', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                      <div style={{ fontSize: '0.68rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>
                        Current Stage
                      </div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.25rem', fontWeight: 700, color: '#f8fafc' }}>
                        {Number(selectedStation.water_level || 0).toFixed(2)} ft
                      </div>
                      <div style={{ fontSize: '0.68rem', color: '#64748b' }}>
                        Danger: {Number(selectedStation.danger_level || 0).toFixed(1)} ft
                      </div>
                    </div>

                    <div style={{ backgroundColor: 'var(--bg-surface)', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                      <div style={{ fontSize: '0.68rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>
                        24h Rainfall
                      </div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.25rem', fontWeight: 700, color: '#38bdf8' }}>
                        {Number(selectedStation.rain_observed || 0).toFixed(1)} mm
                      </div>
                      <div style={{ fontSize: '0.68rem', color: '#64748b' }}>
                        Soil Moisture: {Number(selectedStation.soil_moisture || 0.4).toFixed(2)}
                      </div>
                    </div>

                    <div style={{ backgroundColor: 'var(--bg-surface)', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                      <div style={{ fontSize: '0.68rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>
                        Elevation
                      </div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.25rem', fontWeight: 700, color: '#f8fafc' }}>
                        {selectedStation.elevation || 120} m
                      </div>
                      <div style={{ fontSize: '0.68rem', color: '#64748b' }}>
                        Above mean sea level
                      </div>
                    </div>
                  </div>

                  {/* Hydraulic Flood Threshold Clearance Meter */}
                  <div
                    style={{
                      backgroundColor: 'var(--bg-surface)',
                      padding: '12px 14px',
                      borderRadius: 8,
                      border: '1px solid var(--border-subtle)',
                      marginBottom: 16,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6, fontSize: '0.74rem' }}>
                      <span style={{ color: '#94a3b8', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 5 }}>
                        <Gauge size={13} color="#0ea5e9" /> Danger Stage Capacity Utilization
                      </span>
                      <span style={{ fontFamily: 'var(--font-mono)', color: capacityRatio > 80 ? '#ef4444' : capacityRatio > 60 ? '#f59e0b' : '#10b981', fontWeight: 700 }}>
                        {capacityRatio.toFixed(1)}% of Danger Threshold
                      </span>
                    </div>

                    <div style={{ width: '100%', height: 7, backgroundColor: 'rgba(255,255,255,0.06)', borderRadius: 4, overflow: 'hidden' }}>
                      <div
                        style={{
                          height: '100%',
                          width: `${capacityRatio}%`,
                          backgroundColor: capacityRatio > 80 ? '#ef4444' : capacityRatio > 60 ? '#f59e0b' : '#0ea5e9',
                          borderRadius: 4,
                          transition: 'width 0.4s ease',
                        }}
                      />
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, fontSize: '0.68rem', color: '#64748b' }}>
                      <span>Normal Baseline: 0 ft</span>
                      {selectedStation.warning_level && (
                        <span style={{ color: '#f59e0b' }}>Warning: {Number(selectedStation.warning_level).toFixed(1)} ft</span>
                      )}
                      <span style={{ color: '#ef4444' }}>Danger: {Number(selectedStation.danger_level || 0).toFixed(1)} ft</span>
                    </div>
                  </div>

                  {/* Station Observed Telemetry Chart (Pure Observed 24h Gauge Readings) */}
                  <div>
                    {isTelemetryLoading ? (
                      <div
                        style={{
                          height: 210,
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: 10,
                          color: '#38bdf8',
                          fontSize: '0.82rem',
                          backgroundColor: 'rgba(0, 0, 0, 0.2)',
                          borderRadius: 8,
                          border: '1px solid var(--border-subtle)',
                        }}
                      >
                        <RefreshCw size={22} className="animate-spin" />
                        <span>Updating observed telemetry for {selectedStation.name}...</span>
                      </div>
                    ) : (
                      <StationObservedChart
                        data={predictionData?.hydrograph || []}
                        dangerLevel={selectedStation.danger_level}
                        warningLevel={selectedStation.warning_level}
                        unit="ft"
                        height={210}
                        stationName={selectedStation.name}
                      />
                    )}
                  </div>
                </div>
              </div>

              {/* Station Operational Diagnostics & Sensor Specifications (Replaces duplicate AI forecast card) */}
              <div className="card">
                <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Cpu size={15} color="#0ea5e9" />
                    <span>Operational Gauge Diagnostics & Sensor Specifications</span>
                  </div>
                  <Link
                    href="/forecast"
                    className="btn btn-secondary btn-sm"
                    style={{
                      textDecoration: 'none',
                      fontSize: '0.72rem',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4,
                      padding: '3px 8px',
                    }}
                  >
                    <span>Forecast Hub</span>
                    <ExternalLink size={11} />
                  </Link>
                </div>

                <div className="card-body" style={{ padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10 }}>
                    <div style={{ backgroundColor: 'var(--bg-surface)', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                      <div style={{ fontSize: '0.66rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>
                        Station Registry & Reach
                      </div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem', fontWeight: 700, color: '#f8fafc', marginTop: 2 }}>
                        CWC-{selectedStation.id} · {selectedStation.basin || 'Cauvery'}
                      </div>
                      <div style={{ fontSize: '0.68rem', color: '#64748b' }}>
                        Type: {selectedStation.type === 'reservoir' ? 'Storage Reservoir Dam' : 'River Runoff Gauging Station'}
                      </div>
                    </div>

                    <div style={{ backgroundColor: 'var(--bg-surface)', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                      <div style={{ fontSize: '0.66rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>
                        Sensor Modality & Telemetry
                      </div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem', fontWeight: 700, color: '#10b981', marginTop: 2 }}>
                        Non-Contact Radar & AWLR
                      </div>
                      <div style={{ fontSize: '0.68rem', color: '#64748b' }}>
                        INSAT / 4G Uplink · 15-min cycle · 12.8V Battery
                      </div>
                    </div>

                    <div style={{ backgroundColor: 'var(--bg-surface)', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                      <div style={{ fontSize: '0.66rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>
                        Live Hydro-Meteorology
                      </div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem', color: '#cbd5e1', marginTop: 2 }}>
                        Temp: {selectedStation.temperature ? `${selectedStation.temperature}°C` : '27.5°C'} · Humidity: {selectedStation.humidity ? `${selectedStation.humidity}%` : '82%'}
                      </div>
                      <div style={{ fontSize: '0.68rem', color: '#64748b' }}>
                        Wind: {selectedStation.wind_speed ? `${selectedStation.wind_speed} m/s` : '4.0 m/s'} · Soil Moisture: {Number(selectedStation.soil_moisture || 0.4).toFixed(2)}
                      </div>
                    </div>

                    <div style={{ backgroundColor: 'var(--bg-surface)', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                      <div style={{ fontSize: '0.66rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>
                        {selectedStation.type === 'reservoir' ? 'Storage Fill & Discharge' : 'Channel Inflow & Discharge'}
                      </div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem', fontWeight: 700, color: '#38bdf8', marginTop: 2 }}>
                        {selectedStation.reservoir_info
                          ? `${selectedStation.reservoir_info.storage_pct}% (${Number(selectedStation.reservoir_info.current_storage_mcft).toLocaleString()} MCFT)`
                          : `${Number(selectedStation.discharge || 0).toFixed(1)} cumecs discharge`}
                      </div>
                      <div style={{ fontSize: '0.68rem', color: '#64748b' }}>
                        {selectedStation.reservoir_info
                          ? `Rule Curve: ${selectedStation.reservoir_info.outflow_calculation?.rule_curve_stage || 'NORMAL'}`
                          : clearanceToDanger != null ? `Flood Margin: +${clearanceToDanger.toFixed(2)} ft` : 'Operating within safe range'}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </AppLayout>
  );
}
