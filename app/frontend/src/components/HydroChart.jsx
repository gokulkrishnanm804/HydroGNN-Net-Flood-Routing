/**
 * HydroChart.jsx — Scientific Flood Hydrograph Visualization
 *
 * Features:
 * - 192 points: 96 observed (24h back) + 96 forecast (24h forward)
 * - Gradient CI confidence band (widens with horizon)
 * - Safe / Warning / Danger zone shading via ReferenceArea
 * - Danger + Warning reference lines
 * - Current time marker
 * - Forecast start marker
 * - Peak level marker
 * - Secondary Y-axis for rainfall overlay
 * - Brush (zoom/pan)
 * - Per-point XAI tooltip: rain contribution, upstream, reservoir, confidence
 * - Station comparison (up to 4 stations)
 * - Legend with live colour swatches
 */

import React, { useState, useMemo, useCallback } from 'react';
import {
  ComposedChart,
  Area,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ReferenceArea,
  Brush,
  ResponsiveContainer,
  Label,
} from 'recharts';
import { Activity, Droplet, AlertTriangle, Eye, EyeOff, Maximize2 } from 'lucide-react';

// ─── Colour palette ─────────────────────────────────────────────────────────
const PALETTE = {
  observed:   '#10b981',  // emerald
  forecast:   '#3b82f6',  // blue
  ci_upper:   'rgba(59,130,246,0.12)',
  ci_lower:   '#0b1120',
  rainfall:   '#67e8f9',  // cyan
  discharge:  '#f59e0b',  // amber
  danger:     '#ef4444',
  warning:    '#f97316',
  safe:       'rgba(16,185,129,0.06)',
  flood:      'rgba(239,68,68,0.08)',
  warning_bg: 'rgba(249,115,22,0.06)',
  grid:       'rgba(255,255,255,0.04)',
  axis:       '#475569',
  tick:       '#64748b',
};

// Compare station colours
const COMPARE_COLOURS = ['#a855f7', '#f59e0b', '#06b6d4', '#ec4899'];

// ─── Custom Dot: peak marker ─────────────────────────────────────────────────
const PeakDot = (props) => {
  const { cx, cy, value, payload } = props;
  if (!payload?.is_peak || value == null) return null;
  return (
    <g>
      <circle cx={cx} cy={cy} r={7} fill="none" stroke={PALETTE.danger} strokeWidth={2} />
      <circle cx={cx} cy={cy} r={3} fill={PALETTE.danger} />
      <text x={cx} y={cy - 12} textAnchor="middle" fill={PALETTE.danger} fontSize={9} fontWeight={700}>
        PEAK {value}m
      </text>
    </g>
  );
};

// ─── Custom Tooltip ───────────────────────────────────────────────────────────
const HydroTooltip = ({ active, payload, label, dangerLevel }) => {
  if (!active || !payload || payload.length === 0) return null;

  // Find the primary data point
  const pt = payload[0]?.payload || {};
  const isForecast = pt.section === 'forecast';

  return (
    <div style={{
      background: 'rgba(7,11,22,0.97)',
      border: '1px solid rgba(59,130,246,0.3)',
      borderRadius: '10px',
      padding: '10px 14px',
      minWidth: '220px',
      boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
      fontSize: '0.76rem',
      fontFamily: 'Inter, sans-serif',
    }}>
      {/* Timestamp */}
      <div style={{ color: '#94a3b8', fontWeight: 600, marginBottom: 8, letterSpacing: '0.02em' }}>
        {label} {isForecast ? <span style={{ color: PALETTE.forecast, fontSize: '0.7rem' }}>▶ FORECAST</span> : <span style={{ color: PALETTE.observed, fontSize: '0.7rem' }}>● OBSERVED</span>}
      </div>

      {/* Values */}
      {pt.observed != null && (
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
          <span style={{ color: '#94a3b8' }}>Observed level</span>
          <span style={{ color: PALETTE.observed, fontWeight: 700 }}>{pt.observed} m</span>
        </div>
      )}
      {pt.predicted != null && (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
            <span style={{ color: '#94a3b8' }}>GNN Forecast</span>
            <span style={{ color: PALETTE.forecast, fontWeight: 700 }}>{pt.predicted} m</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, opacity: 0.7 }}>
            <span style={{ color: '#64748b' }}>95% CI</span>
            <span style={{ color: '#64748b' }}>[{pt.lower} – {pt.upper}]</span>
          </div>
        </>
      )}

      {/* Danger ratio */}
      {dangerLevel && (pt.observed ?? pt.predicted) != null && (
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
          <span style={{ color: '#94a3b8' }}>Danger ratio</span>
          <span style={{ color: (pt.observed ?? pt.predicted) / dangerLevel > 0.9 ? PALETTE.danger : '#94a3b8', fontWeight: 600 }}>
            {(((pt.observed ?? pt.predicted) / dangerLevel) * 100).toFixed(1)}%
          </span>
        </div>
      )}

      {/* Rainfall */}
      {pt.rainfall_mm != null && pt.rainfall_mm > 0 && (
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
          <span style={{ color: '#94a3b8' }}>Rainfall</span>
          <span style={{ color: PALETTE.rainfall }}>{pt.rainfall_mm} mm</span>
        </div>
      )}

      {/* XAI breakdown — only for forecast points */}
      {isForecast && (pt.rain_contribution_m > 0 || pt.upstream_contribution_m > 0 || pt.reservoir_contribution_m > 0) && (
        <>
          <div style={{ borderTop: '1px solid rgba(255,255,255,0.07)', margin: '6px 0 5px', paddingTop: 5, color: '#64748b', fontSize: '0.7rem', letterSpacing: '0.05em' }}>
            DRIVER ATTRIBUTION
          </div>
          {pt.rain_contribution_m > 0 && (
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
              <span style={{ color: '#94a3b8' }}>🌧 Rainfall runoff</span>
              <span style={{ color: PALETTE.rainfall }}>+{pt.rain_contribution_m.toFixed(3)} m</span>
            </div>
          )}
          {pt.upstream_contribution_m > 0 && (
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
              <span style={{ color: '#94a3b8' }}>🔁 Upstream flow</span>
              <span style={{ color: PALETTE.discharge }}>+{pt.upstream_contribution_m.toFixed(3)} m</span>
            </div>
          )}
          {pt.reservoir_contribution_m > 0 && (
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
              <span style={{ color: '#94a3b8' }}>🏛 Reservoir release</span>
              <span style={{ color: '#a855f7' }}>+{pt.reservoir_contribution_m.toFixed(3)} m</span>
            </div>
          )}
        </>
      )}

      {/* Confidence */}
      {pt.confidence != null && (
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
          <span style={{ color: '#94a3b8' }}>Model confidence</span>
          <span style={{ color: pt.confidence > 0.8 ? '#10b981' : pt.confidence > 0.6 ? '#f59e0b' : '#ef4444', fontWeight: 600 }}>
            {(pt.confidence * 100).toFixed(0)}%
          </span>
        </div>
      )}

      {/* Source */}
      <div style={{ marginTop: 5, fontSize: '0.67rem', color: '#334155' }}>
        Source: {pt.source || '—'}
      </div>
    </div>
  );
};

// ─── Legend entries ──────────────────────────────────────────────────────────
const LegendEntry = ({ colour, label, dash = false, swatch = 'line' }) => (
  <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: '0.72rem', color: '#94a3b8' }}>
    {swatch === 'line' ? (
      <svg width={22} height={8}>
        <line x1={0} y1={4} x2={22} y2={4} stroke={colour} strokeWidth={2}
          strokeDasharray={dash ? '5 3' : 'none'} />
      </svg>
    ) : swatch === 'area' ? (
      <span style={{ display: 'inline-block', width: 16, height: 10, background: colour, borderRadius: 2 }} />
    ) : (
      <span style={{ display: 'inline-block', width: 10, height: 10, background: colour, borderRadius: '50%' }} />
    )}
    {label}
  </span>
);

// ─── Overlay toggle button ────────────────────────────────────────────────────
const ToggleBtn = ({ active, onClick, children }) => (
  <button onClick={onClick} style={{
    padding: '3px 10px', borderRadius: 5, border: `1px solid ${active ? 'rgba(6,182,212,0.5)' : 'rgba(255,255,255,0.08)'}`,
    background: active ? 'rgba(6,182,212,0.1)' : 'transparent',
    color: active ? '#06b6d4' : '#64748b', fontSize: '0.72rem', cursor: 'pointer',
    transition: 'all 0.15s', display: 'flex', alignItems: 'center', gap: 4,
  }}>
    {active ? <Eye size={11}/> : <EyeOff size={11}/>} {children}
  </button>
);

// ─── Main Component ──────────────────────────────────────────────────────────
const HydroChart = ({
  predictionData,
  stationName = '',
  loading = false,
  compareData = [],        // array of {stationId, stationName, predictionData}
  onStationRemove = null,
}) => {
  const [showRainfall, setShowRainfall]   = useState(true);
  const [showDischarge, setShowDischarge] = useState(false);
  const [showZones, setShowZones]         = useState(true);
  const [showCI, setShowCI]               = useState(true);
  const [brushRange, setBrushRange]       = useState(null);

  // ── Compute derived chart data ─────────────────────────────────────────────
  const { chartData, peakIdx, forecastStartIdx, rainfallMax, dangerLevel, warnLevel, safeLevel } = useMemo(() => {
    if (!predictionData?.hydrograph) return { chartData: [], peakIdx: -1, forecastStartIdx: -1, rainfallMax: 10, dangerLevel: 100, warnLevel: 80, safeLevel: 50 };

    const hg = predictionData.hydrograph;
    const danger = predictionData.danger_level_m ?? 100;
    const warn   = predictionData.warning_level_m ?? danger * 0.8;
    const safe   = predictionData.safe_level_m   ?? danger * 0.5;

    let peakVal = -Infinity, peakI = -1, firstFcIdx = -1;
    let rainMax = 10;

    const data = hg.map((pt, i) => {
      const lvl = pt.observed ?? pt.predicted;
      if (pt.section === 'forecast') {
        if (firstFcIdx === -1) firstFcIdx = i;
        if (lvl != null && lvl > peakVal) { peakVal = lvl; peakI = i; }
      }
      if (pt.rainfall_mm != null && pt.rainfall_mm > rainMax) rainMax = pt.rainfall_mm;
      return {
        ...pt,
        // Null out CI when toggle is off — Recharts still renders nulls as gaps
        upper_ci: pt.upper,
        lower_ci: pt.lower,
        is_peak: false,
      };
    });

    if (peakI > -1) data[peakI].is_peak = true;

    return {
      chartData: data,
      peakIdx:   peakI,
      forecastStartIdx: firstFcIdx,
      rainfallMax: rainMax,
      dangerLevel: danger,
      warnLevel:   warn,
      safeLevel:   safe,
    };
  }, [predictionData]);

  // X-axis interval to avoid label crowding (target ~10 visible labels)
  const tickInterval = useMemo(() => {
    const n = chartData.length;
    if (n <= 20) return 1;
    if (n <= 48) return 3;
    if (n <= 96) return 7;
    return Math.floor(n / 18);
  }, [chartData.length]);

  // Transition time label for reference line
  const transitionTime = forecastStartIdx > 0 ? chartData[forecastStartIdx]?.time : null;

  // Peak time
  const peakTime = peakIdx > -1 ? chartData[peakIdx]?.time : null;

  if (loading) {
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12 }}>
        <div style={{ width: 40, height: 40, border: '3px solid rgba(59,130,246,0.2)', borderTop: '3px solid #3b82f6', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
        <span style={{ color: '#94a3b8', fontSize: '0.875rem' }}>Running Nash-Sutcliffe routing…</span>
        <span style={{ color: '#475569', fontSize: '0.75rem' }}>Evaluating 192 hydrograph points</span>
      </div>
    );
  }

  if (!predictionData || chartData.length === 0) {
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
        <Activity size={32} color="#334155" />
        <span style={{ color: '#475569', fontSize: '0.875rem' }}>Select a station to generate the hydrograph</span>
      </div>
    );
  }

  // ── Routing metadata badge ─────────────────────────────────────────────────
  const meta = predictionData.routing_metadata || {};

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 0 }}>

      {/* ── Header row ───────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
        <div>
          <h3 style={{ fontSize: '0.9rem', color: '#f8fafc', display: 'flex', alignItems: 'center', gap: 6, margin: 0 }}>
            <Activity size={15} color="#06b6d4" />
            Hydrograph — {stationName || predictionData.station_id}
            <span style={{ fontSize: '0.68rem', color: '#475569', background: 'rgba(71,85,105,0.2)', padding: '1px 7px', borderRadius: 4, fontWeight: 400, letterSpacing: '0.05em' }}>
              {meta.method || 'Nash-Sutcliffe IUH + Pchip'}
            </span>
          </h3>
          {/* Routing summary badges */}
          <div style={{ display: 'flex', gap: 8, marginTop: 5, flexWrap: 'wrap' }}>
            {meta.rain_24h_mm != null && (
              <span style={{ fontSize: '0.67rem', color: PALETTE.rainfall, background: 'rgba(103,232,249,0.08)', padding: '1px 7px', borderRadius: 3 }}>
                🌧 {meta.rain_24h_mm} mm / 24h
              </span>
            )}
            {meta.soil_moisture != null && (
              <span style={{ fontSize: '0.67rem', color: '#a78bfa', background: 'rgba(167,139,250,0.08)', padding: '1px 7px', borderRadius: 3 }}>
                🌱 SM {(meta.soil_moisture * 100).toFixed(0)}%
              </span>
            )}
            {meta.upstream_discharge_cumecs > 0 && (
              <span style={{ fontSize: '0.67rem', color: PALETTE.discharge, background: 'rgba(245,158,11,0.08)', padding: '1px 7px', borderRadius: 3 }}>
                ⬆ {meta.upstream_discharge_cumecs} m³/s upstream
              </span>
            )}
            {meta.reservoir_release_cumecs > 0 && (
              <span style={{ fontSize: '0.67rem', color: '#c084fc', background: 'rgba(192,132,252,0.08)', padding: '1px 7px', borderRadius: 3 }}>
                🏛 {meta.reservoir_release_cumecs} m³/s release
              </span>
            )}
            <span style={{ fontSize: '0.67rem', color: '#475569', padding: '1px 4px' }}>
              {meta.observed_points || '?'} obs + {meta.forecast_points || '?'} fc pts
            </span>
          </div>
        </div>

        {/* Overlay toggles */}
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <ToggleBtn active={showCI} onClick={() => setShowCI(v => !v)}>95% CI</ToggleBtn>
          <ToggleBtn active={showZones} onClick={() => setShowZones(v => !v)}>Zones</ToggleBtn>
          <ToggleBtn active={showRainfall} onClick={() => setShowRainfall(v => !v)}>
            <Droplet size={10} /> Rainfall
          </ToggleBtn>
          <ToggleBtn active={showDischarge} onClick={() => setShowDischarge(v => !v)}>Discharge</ToggleBtn>
        </div>
      </div>

      {/* ── Legend row ───────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 6, flexWrap: 'wrap', paddingLeft: 2 }}>
        <LegendEntry colour={PALETTE.observed}  label="Observed (24h)" />
        <LegendEntry colour={PALETTE.forecast}  label="GNN Forecast (24h)" dash />
        <LegendEntry colour="rgba(59,130,246,0.25)" label="95% CI band" swatch="area" />
        <LegendEntry colour={PALETTE.danger}    label={`Danger (${dangerLevel}m)`} dash swatch="line" />
        <LegendEntry colour={PALETTE.warning}   label={`Warning (${warnLevel.toFixed(1)}m)`} dash swatch="line" />
        {showRainfall && <LegendEntry colour={PALETTE.rainfall} label="Rainfall (mm)" swatch="area" />}
        {compareData.map((c, i) => (
          <LegendEntry key={c.stationId} colour={COMPARE_COLOURS[i]} label={c.stationName} />
        ))}
      </div>

      {/* ── Chart ────────────────────────────────────────────────────────────── */}
      <div style={{ flex: 1, minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={chartData}
            margin={{ top: 6, right: showRainfall ? 52 : 16, left: -8, bottom: 30 }}
            syncId="hydro"
          >
            <defs>
              {/* CI gradient fill */}
              <linearGradient id="ciGradFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor="#3b82f6" stopOpacity={0.22} />
                <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.03} />
              </linearGradient>
              {/* Observed area gradient */}
              <linearGradient id="obsAreaFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor="#10b981" stopOpacity={0.12} />
                <stop offset="100%" stopColor="#10b981" stopOpacity={0.0} />
              </linearGradient>
              {/* Rainfall bar gradient */}
              <linearGradient id="rainFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor="#67e8f9" stopOpacity={0.8} />
                <stop offset="100%" stopColor="#67e8f9" stopOpacity={0.2} />
              </linearGradient>
            </defs>

            <CartesianGrid strokeDasharray="3 3" stroke={PALETTE.grid} vertical={false} />

            {/* X axis */}
            <XAxis
              dataKey="time"
              stroke={PALETTE.axis}
              tick={{ fill: PALETTE.tick, fontSize: 9 }}
              interval={tickInterval}
              angle={-30}
              textAnchor="end"
              height={42}
            />

            {/* Primary Y axis — water level */}
            <YAxis
              yAxisId="level"
              stroke={PALETTE.axis}
              tick={{ fill: PALETTE.tick, fontSize: 10 }}
              domain={['auto', (dataMax) => Math.max(dataMax * 1.05, dangerLevel * 1.05)]}
              tickFormatter={v => `${v}m`}
              width={52}
              label={{ value: 'Water Level (m)', angle: -90, position: 'insideLeft', fill: '#475569', fontSize: 10, dy: 50 }}
            />

            {/* Secondary Y axis — rainfall */}
            {showRainfall && (
              <YAxis
                yAxisId="rain"
                orientation="right"
                stroke={PALETTE.axis}
                tick={{ fill: PALETTE.tick, fontSize: 9 }}
                domain={[0, (dataMax) => Math.max(dataMax * 1.5, rainfallMax * 1.5, 10)]}
                tickFormatter={v => `${v}mm`}
                width={46}
                label={{ value: 'Rainfall (mm)', angle: 90, position: 'insideRight', fill: '#475569', fontSize: 10, dy: -40 }}
              />
            )}

            <Tooltip content={<HydroTooltip dangerLevel={dangerLevel} />} />

            {/* ── Zone shading ─────────────────────────────────────────────── */}
            {showZones && (
              <>
                {/* Safe zone: 0 – warnLevel */}
                <ReferenceArea yAxisId="level" y1={0} y2={safeLevel}
                  fill={PALETTE.safe} fillOpacity={1} stroke="none" />
                {/* Warning zone: warnLevel – dangerLevel */}
                <ReferenceArea yAxisId="level" y1={safeLevel} y2={warnLevel}
                  fill={PALETTE.warning_bg} fillOpacity={1} stroke="none" />
                {/* Flood zone: above dangerLevel */}
                <ReferenceArea yAxisId="level" y1={dangerLevel} y2={dangerLevel * 1.5}
                  fill={PALETTE.flood} fillOpacity={1} stroke="none" />
              </>
            )}

            {/* ── Danger / Warning reference lines ─────────────────────────── */}
            <ReferenceLine yAxisId="level" y={dangerLevel}
              stroke={PALETTE.danger} strokeDasharray="6 3" strokeWidth={1.5}
              label={<Label value={`⚠ Danger ${dangerLevel}m`} position="insideTopRight" fill={PALETTE.danger} fontSize={9} />}
            />
            <ReferenceLine yAxisId="level" y={warnLevel}
              stroke={PALETTE.warning} strokeDasharray="4 2" strokeWidth={1}
              label={<Label value={`Warning ${warnLevel.toFixed(1)}m`} position="insideTopRight" fill={PALETTE.warning} fontSize={9} />}
            />

            {/* ── Forecast start vertical marker ────────────────────────────── */}
            {transitionTime && (
              <ReferenceLine yAxisId="level" x={transitionTime}
                stroke="rgba(255,255,255,0.15)" strokeWidth={1.5} strokeDasharray="2 2"
                label={<Label value="NOW →" position="top" fill="rgba(255,255,255,0.35)" fontSize={9} />}
              />
            )}

            {/* ── Peak marker ──────────────────────────────────────────────── */}
            {peakTime && (
              <ReferenceLine yAxisId="level" x={peakTime}
                stroke={PALETTE.danger} strokeDasharray="3 3" strokeWidth={1} strokeOpacity={0.5}
              />
            )}

            {/* ── Rainfall bars (secondary axis) ───────────────────────────── */}
            {showRainfall && (
              <Bar
                yAxisId="rain"
                dataKey="rainfall_mm"
                name="Rainfall"
                fill="url(#rainFill)"
                opacity={0.7}
                maxBarSize={6}
                isAnimationActive={false}
              />
            )}

            {/* ── CI band ──────────────────────────────────────────────────── */}
            {showCI && (
              <>
                <Area
                  yAxisId="level"
                  type="monotone"
                  dataKey="upper_ci"
                  stroke="rgba(59,130,246,0.2)"
                  strokeWidth={0.5}
                  fill="url(#ciGradFill)"
                  connectNulls={false}
                  isAnimationActive={false}
                  dot={false}
                  name="upper_ci"
                  legendType="none"
                />
                <Area
                  yAxisId="level"
                  type="monotone"
                  dataKey="lower_ci"
                  stroke="rgba(59,130,246,0.2)"
                  strokeWidth={0.5}
                  fill={PALETTE.ci_lower}
                  connectNulls={false}
                  isAnimationActive={false}
                  dot={false}
                  name="lower_ci"
                  legendType="none"
                />
              </>
            )}

            {/* ── Observed level — solid green with subtle fill ──────────────── */}
            <Area
              yAxisId="level"
              type="monotone"
              dataKey="observed"
              name="Observed"
              stroke={PALETTE.observed}
              strokeWidth={2.5}
              fill="url(#obsAreaFill)"
              connectNulls={false}
              isAnimationActive={true}
              animationDuration={1200}
              dot={false}
              activeDot={{ r: 5, fill: PALETTE.observed, stroke: '#0b1120', strokeWidth: 2 }}
            />

            {/* ── Forecast line — dashed blue ─────────────────────────────── */}
            <Line
              yAxisId="level"
              type="monotone"
              dataKey="predicted"
              name="GNN Forecast"
              stroke={PALETTE.forecast}
              strokeWidth={2.5}
              strokeDasharray="8 4"
              connectNulls={false}
              isAnimationActive={true}
              animationDuration={1500}
              animationBegin={300}
              dot={false}
              activeDot={{ r: 5, fill: PALETTE.forecast, stroke: '#0b1120', strokeWidth: 2 }}
            />

            {/* ── Compare station lines ────────────────────────────────────── */}
            {compareData.map((cmp, ci) => {
              if (!cmp.predictionData?.hydrograph) return null;
              // Join the compare hydrograph onto the same time index
              return (
                <Line
                  key={cmp.stationId}
                  yAxisId="level"
                  type="monotone"
                  dataKey={`compare_${ci}`}
                  name={cmp.stationName}
                  stroke={COMPARE_COLOURS[ci]}
                  strokeWidth={2}
                  strokeDasharray="5 2"
                  connectNulls={false}
                  isAnimationActive={false}
                  dot={false}
                />
              );
            })}

            {/* ── Brush (zoom/pan) ─────────────────────────────────────────── */}
            <Brush
              dataKey="time"
              height={18}
              y={0}
              fill="rgba(15,23,42,0.8)"
              stroke="rgba(59,130,246,0.25)"
              travellerWidth={6}
              startIndex={Math.max(0, (forecastStartIdx > 0 ? forecastStartIdx : 0) - 32)}
            >
              <ComposedChart>
                <Line yAxisId="level" dataKey="observed" stroke={PALETTE.observed} dot={false} strokeWidth={1} />
                <Line yAxisId="level" dataKey="predicted" stroke={PALETTE.forecast} dot={false} strokeWidth={1} />
              </ComposedChart>
            </Brush>
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default HydroChart;
