'use client';
import React, { useMemo, useState } from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from 'recharts';
import { Eye, ZoomIn, ZoomOut, AlertTriangle, ShieldCheck } from 'lucide-react';

interface HydrographPoint {
  time: string;
  ts_iso?: string;
  section?: 'observed' | 'forecast';
  observed?: number | null;
  predicted?: number | null;
  upper?: number | null;
  lower?: number | null;
  discharge?: number | null;
  rainfall_mm?: number | null;
}

interface HydrographChartProps {
  data: HydrographPoint[];
  dangerLevel?: number;
  warningLevel?: number;
  unit?: string;
  height?: number;
  title?: string;
}

const CustomTooltip = ({ active, payload, label, unit = 'ft' }: any) => {
  if (!active || !payload?.length) return null;

  const rawPoint = payload[0]?.payload;
  const isForecast = rawPoint?.section === 'forecast';

  return (
    <div
      style={{
        backgroundColor: '#0c1524',
        border: '1px solid rgba(56, 189, 248, 0.25)',
        borderRadius: 8,
        padding: '12px 16px',
        boxShadow: '0 8px 24px rgba(0, 0, 0, 0.65)',
        fontSize: '0.8rem',
        minWidth: 210,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: 6 }}>
        <span style={{ color: '#94a3b8', fontWeight: 600 }}>{label}</span>
        <span
          style={{
            fontSize: '0.68rem',
            padding: '2px 7px',
            borderRadius: 4,
            fontWeight: 700,
            textTransform: 'uppercase',
            backgroundColor: isForecast ? 'rgba(56, 189, 248, 0.15)' : 'rgba(2, 132, 199, 0.18)',
            color: isForecast ? '#38bdf8' : '#38bdf8',
            border: `1px solid ${isForecast ? 'rgba(56, 189, 248, 0.3)' : 'rgba(2, 132, 199, 0.3)'}`,
          }}
        >
          {isForecast ? 'GNN Forecast' : 'Observed'}
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {rawPoint?.observed != null && (
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, color: '#38bdf8' }}>
            <span>Observed Stage:</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700 }}>
              {Number(rawPoint.observed).toFixed(2)} {unit}
            </span>
          </div>
        )}

        {rawPoint?.predicted != null && (
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, color: '#38bdf8' }}>
            <span>Predicted Level:</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700 }}>
              {Number(rawPoint.predicted).toFixed(2)} {unit}
            </span>
          </div>
        )}

        {rawPoint?.upper != null && rawPoint?.lower != null && isForecast && (
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, color: '#94a3b8', fontSize: '0.74rem' }}>
            <span>95% CI Range:</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: '#cbd5e1' }}>
              [{Number(rawPoint.lower).toFixed(2)} – {Number(rawPoint.upper).toFixed(2)}] {unit}
            </span>
          </div>
        )}

        {rawPoint?.discharge != null && (
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, color: '#64748b', fontSize: '0.74rem' }}>
            <span>Discharge:</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 500, color: '#94a3b8' }}>
              {Number(rawPoint.discharge).toFixed(1)} cumecs
            </span>
          </div>
        )}

        {rawPoint?.rainfall_mm != null && rawPoint.rainfall_mm > 0 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, color: '#38bdf8', fontSize: '0.74rem' }}>
            <span>Rainfall:</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 500 }}>
              {Number(rawPoint.rainfall_mm).toFixed(1)} mm
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

export default function HydrographChart({
  data,
  dangerLevel,
  warningLevel,
  unit = 'ft',
  height = 360,
  title,
}: HydrographChartProps) {
  // View mode: 'auto' zooms to hydrograph dynamics; 'full' includes high threshold reference lines
  const [viewMode, setViewMode] = useState<'auto' | 'full'>('auto');

  // Find transition timestamp between observed and forecast
  const lastObsIndex = useMemo(() => {
    if (!data || data.length === 0) return -1;
    return data.reduce((last, pt, idx) => (pt.observed != null ? idx : last), -1);
  }, [data]);

  const nowTime = useMemo(() => {
    if (lastObsIndex >= 0 && data[lastObsIndex]) {
      return data[lastObsIndex].time;
    }
    return null;
  }, [data, lastObsIndex]);

  // Transform data to support stacked CI area rendering (lower + span)
  const chartData = useMemo(() => {
    if (!data || data.length === 0) return [];

    const lastObsVal = lastObsIndex >= 0 ? data[lastObsIndex].observed : null;

    return data.map((pt, idx) => {
      const isBridge = idx === lastObsIndex;
      const forecastVal = isBridge ? lastObsVal : pt.predicted;
      const upperVal = isBridge ? lastObsVal : pt.upper;
      const lowerVal = isBridge ? lastObsVal : pt.lower;

      // For stacked area representing the confidence band [lower, upper]:
      const ciBase = lowerVal != null ? lowerVal : null;
      const ciSpan = upperVal != null && lowerVal != null ? Math.max(0, upperVal - lowerVal) : null;

      return {
        ...pt,
        display_observed: pt.observed,
        display_forecast: forecastVal,
        ci_base: ciBase,
        ci_span: ciSpan,
        display_upper: upperVal,
        display_lower: lowerVal,
      };
    });
  }, [data, lastObsIndex]);

  // Calculate actual data bounds
  const { dataMin, dataMax, currentLevel } = useMemo(() => {
    let min = Infinity;
    let max = -Infinity;
    let current = null;

    data.forEach((d) => {
      [d.observed, d.predicted, d.upper, d.lower].forEach((v) => {
        if (v != null && !isNaN(v)) {
          if (v < min) min = v;
          if (v > max) max = v;
        }
      });
    });

    if (lastObsIndex >= 0 && data[lastObsIndex]?.observed != null) {
      current = data[lastObsIndex].observed;
    }

    return {
      dataMin: min === Infinity ? 0 : min,
      dataMax: max === -Infinity ? 100 : max,
      currentLevel: current,
    };
  }, [data, lastObsIndex]);

  // Compute sensible Y domain based on viewMode
  const yDomain = useMemo(() => {
    if (viewMode === 'full') {
      let maxVal = Math.max(dataMax, dangerLevel || 0, warningLevel || 0);
      let minVal = Math.min(dataMin, 0);
      const pad = (maxVal - minVal) * 0.08 || 10;
      return [Math.max(0, Math.floor(minVal - pad)), Math.ceil(maxVal + pad)];
    }

    // Auto Focus Mode: focus on the hydrograph curve with comfortable headroom
    const span = Math.max(dataMax - dataMin, 1.0);
    const pad = Math.max(span * 0.25, 3.0);
    let yMin = Math.max(0, Math.floor(dataMin - pad));
    let yMax = Math.ceil(dataMax + pad);

    // If warning/danger level is within 15% of the curve, include it
    if (warningLevel && warningLevel <= yMax * 1.15 && warningLevel >= yMin) {
      yMax = Math.max(yMax, Math.ceil(warningLevel + pad * 0.5));
    }
    if (dangerLevel && dangerLevel <= yMax * 1.15 && dangerLevel >= yMin) {
      yMax = Math.max(yMax, Math.ceil(dangerLevel + pad * 0.5));
    }

    return [yMin, yMax];
  }, [dataMin, dataMax, dangerLevel, warningLevel, viewMode]);

  // Headroom to danger calculation
  const headroomToDanger = useMemo(() => {
    if (dangerLevel && currentLevel != null) {
      const diff = dangerLevel - currentLevel;
      return diff > 0 ? diff : 0;
    }
    return null;
  }, [dangerLevel, currentLevel]);

  if (!data || data.length === 0) {
    return (
      <div
        style={{
          height,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: 'rgba(255, 255, 255, 0.02)',
          borderRadius: 8,
          border: '1px solid var(--border-subtle)',
          color: '#64748b',
          fontSize: '0.85rem',
        }}
      >
        No hydrograph telemetry available.
      </div>
    );
  }

  return (
    <div style={{ width: '100%' }}>
      {/* Header bar with title, legend, and auto-focus toggle */}
      <div
        style={{
          marginBottom: 14,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 12,
        }}
      >
        <div>
          {title && (
            <h4 style={{ fontSize: '0.9rem', color: '#f1f5f9', fontWeight: 600, margin: 0 }}>
              {title}
            </h4>
          )}
          {headroomToDanger != null && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 3, fontSize: '0.72rem', color: '#94a3b8' }}>
              <ShieldCheck size={13} color="#10b981" />
              <span>
                Clearance to Danger Threshold: <strong style={{ color: '#10b981' }}>{headroomToDanger.toFixed(1)} {unit}</strong>
              </span>
            </div>
          )}
        </div>

        {/* Legend & Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: '0.72rem', color: '#94a3b8' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 14, height: 2.5, backgroundColor: '#0284c7', display: 'inline-block', borderRadius: 1 }} />
              Observed Past 24h
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 14, height: 2, borderTop: '2px dashed #38bdf8', display: 'inline-block' }} />
              HydroGNN-Net Forecast
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 12, height: 8, backgroundColor: 'rgba(56, 189, 248, 0.22)', display: 'inline-block', borderRadius: 2 }} />
              95% Confidence Band
            </span>
            {dangerLevel && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <span style={{ width: 12, height: 2, backgroundColor: '#ef4444', display: 'inline-block' }} />
                Danger ({dangerLevel} {unit})
              </span>
            )}
          </div>

          {/* View Mode Toggle Button */}
          <div
            style={{
              display: 'inline-flex',
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-medium)',
              borderRadius: 6,
              padding: 2,
            }}
          >
            <button
              type="button"
              onClick={() => setViewMode('auto')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 5,
                padding: '4px 9px',
                fontSize: '0.7rem',
                fontWeight: 600,
                borderRadius: 4,
                border: 'none',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
                backgroundColor: viewMode === 'auto' ? '#0284c7' : 'transparent',
                color: viewMode === 'auto' ? '#ffffff' : '#94a3b8',
              }}
              title="Focus Y-axis on hydrograph wave variation"
            >
              <ZoomIn size={12} />
              Auto Focus
            </button>
            <button
              type="button"
              onClick={() => setViewMode('full')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 5,
                padding: '4px 9px',
                fontSize: '0.7rem',
                fontWeight: 600,
                borderRadius: 4,
                border: 'none',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
                backgroundColor: viewMode === 'full' ? '#0284c7' : 'transparent',
                color: viewMode === 'full' ? '#ffffff' : '#94a3b8',
              }}
              title="Expand Y-axis to full capacity & danger threshold"
            >
              <ZoomOut size={12} />
              Full Scale
            </button>
          </div>
        </div>
      </div>

      {/* Chart Canvas */}
      <div style={{ width: '100%', height }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 12, right: 14, left: -10, bottom: 4 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.06)" strokeDasharray="3 3" vertical={false} />

            <XAxis
              dataKey="time"
              stroke="#64748b"
              fontSize={11}
              tickLine={false}
              interval="preserveStartEnd"
              minTickGap={45}
            />

            <YAxis
              stroke="#64748b"
              fontSize={11}
              domain={yDomain}
              tickLine={false}
              unit={` ${unit}`}
            />

            <Tooltip content={<CustomTooltip unit={unit} />} />

            {/* Vertical Marker separating Past (Observed) and Future (Forecast) */}
            {nowTime && (
              <ReferenceLine
                x={nowTime}
                stroke="#0ea5e9"
                strokeDasharray="3 3"
                strokeWidth={1.5}
                label={{
                  value: 'Current (Now)',
                  fill: '#38bdf8',
                  fontSize: 10,
                  position: 'insideTopLeft',
                  offset: 8,
                }}
              />
            )}

            {/* Threshold Reference Lines (shown when in range or Full Scale) */}
            {dangerLevel && dangerLevel <= yDomain[1] && dangerLevel >= yDomain[0] && (
              <ReferenceLine
                y={dangerLevel}
                stroke="#ef4444"
                strokeDasharray="4 4"
                strokeWidth={1.5}
                label={{
                  value: `Danger: ${dangerLevel}${unit}`,
                  fill: '#ef4444',
                  fontSize: 10,
                  position: 'insideTopRight',
                }}
              />
            )}

            {warningLevel && warningLevel <= yDomain[1] && warningLevel >= yDomain[0] && (
              <ReferenceLine
                y={warningLevel}
                stroke="#f59e0b"
                strokeDasharray="3 3"
                strokeWidth={1}
                label={{
                  value: `Warning: ${warningLevel}${unit}`,
                  fill: '#f59e0b',
                  fontSize: 10,
                  position: 'insideTopRight',
                }}
              />
            )}

            {/* 95% Confidence Interval Band (Stacked Area) */}
            <Area
              type="monotone"
              dataKey="ci_base"
              stackId="ci"
              stroke="transparent"
              fill="transparent"
              isAnimationActive={false}
              name="CI Lower"
            />
            <Area
              type="monotone"
              dataKey="ci_span"
              stackId="ci"
              stroke="transparent"
              fill="rgba(56, 189, 248, 0.18)"
              isAnimationActive={false}
              name="95% CI Range"
            />

            {/* Historical Observed Stage (Solid Line) */}
            <Line
              type="monotone"
              dataKey="display_observed"
              stroke="#0284c7"
              strokeWidth={2.4}
              dot={false}
              name="Observed Stage"
              isAnimationActive={false}
            />

            {/* HydroGNN-Net Forecast Stage (Dashed Line) */}
            <Line
              type="monotone"
              dataKey="display_forecast"
              stroke="#38bdf8"
              strokeWidth={2.2}
              strokeDasharray="5 4"
              dot={false}
              name="GNN Forecast"
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
