'use client';
import React, { useMemo, useState } from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from 'recharts';
import { Eye, ZoomIn, ZoomOut, AlertTriangle, ShieldCheck, Activity } from 'lucide-react';

interface TelemetryPoint {
  time: string;
  ts_iso?: string;
  observed?: number | null;
  discharge?: number | null;
  rainfall_mm?: number | null;
}

interface StationObservedChartProps {
  data: TelemetryPoint[];
  dangerLevel?: number | null;
  warningLevel?: number | null;
  unit?: string;
  height?: number;
  stationName?: string;
}

const CustomObservedTooltip = ({ active, payload, label, unit = 'ft' }: any) => {
  if (!active || !payload?.length) return null;

  const rawPoint = payload[0]?.payload;

  return (
    <div
      style={{
        backgroundColor: '#0c1524',
        border: '1px solid rgba(56, 189, 248, 0.3)',
        borderRadius: 8,
        padding: '12px 16px',
        boxShadow: '0 8px 24px rgba(0, 0, 0, 0.7)',
        fontSize: '0.8rem',
        minWidth: 200,
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 8,
          borderBottom: '1px solid rgba(255,255,255,0.08)',
          paddingBottom: 6,
        }}
      >
        <span style={{ color: '#94a3b8', fontWeight: 600 }}>{label}</span>
        <span
          style={{
            fontSize: '0.68rem',
            padding: '2px 7px',
            borderRadius: 10,
            backgroundColor: 'rgba(56, 189, 248, 0.15)',
            color: '#38bdf8',
            border: '1px solid rgba(56, 189, 248, 0.35)',
            fontWeight: 600,
            textTransform: 'uppercase',
          }}
        >
          Recorded Telemetry
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        {rawPoint?.observed != null && (
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, color: '#f8fafc' }}>
            <span style={{ color: '#94a3b8' }}>Observed Stage:</span>
            <strong style={{ fontFamily: 'var(--font-mono)', color: '#38bdf8' }}>
              {Number(rawPoint.observed).toFixed(2)} {unit}
            </strong>
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

        {rawPoint?.rainfall_mm != null && (
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

export default function StationObservedChart({
  data,
  dangerLevel,
  warningLevel,
  unit = 'ft',
  height = 220,
  stationName = 'Station',
}: StationObservedChartProps) {
  const [viewMode, setViewMode] = useState<'auto' | 'full'>('auto');

  // Filter to valid observed points
  const observedPoints = useMemo(() => {
    return (data || []).filter((pt) => pt.observed != null);
  }, [data]);

  // Telemetry statistics
  const stats = useMemo(() => {
    if (observedPoints.length === 0) return { peak: null, peakTime: '', min: null, current: null, trend: 'Steady' };

    let maxVal = -Infinity;
    let minVal = Infinity;
    let maxTime = '';

    observedPoints.forEach((pt) => {
      const val = Number(pt.observed);
      if (val > maxVal) {
        maxVal = val;
        maxTime = pt.time;
      }
      if (val < minVal) {
        minVal = val;
      }
    });

    const currentVal = Number(observedPoints[observedPoints.length - 1].observed);
    const prevVal = observedPoints.length > 4 ? Number(observedPoints[observedPoints.length - 5].observed) : currentVal;
    const diff = currentVal - prevVal;
    let trend = 'Steady';
    if (diff > 0.05) trend = `Rising (+${diff.toFixed(2)} ${unit})`;
    else if (diff < -0.05) trend = `Falling (${diff.toFixed(2)} ${unit})`;

    return {
      peak: maxVal !== -Infinity ? maxVal : null,
      peakTime: maxTime,
      min: minVal !== Infinity ? minVal : null,
      current: currentVal,
      trend,
    };
  }, [observedPoints, unit]);

  // Compute Y-Axis Domain
  const yDomain = useMemo(() => {
    if (observedPoints.length === 0) return [0, 100];

    const vals = observedPoints.map((pt) => Number(pt.observed));
    const minObs = Math.min(...vals);
    const maxObs = Math.max(...vals);

    if (viewMode === 'full') {
      const upperLim = Math.max(maxObs, Number(dangerLevel || 0), Number(warningLevel || 0));
      return [0, Math.ceil(upperLim * 1.08)];
    }

    // Auto-focus around observed telemetry dynamics
    const pad = Math.max((maxObs - minObs) * 0.25, 1.5);
    return [
      Math.max(0, Math.floor((minObs - pad) * 10) / 10),
      Math.ceil((maxObs + pad) * 10) / 10,
    ];
  }, [observedPoints, dangerLevel, warningLevel, viewMode]);

  return (
    <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* Header bar with Mode Controls & Observed Stats */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Activity size={15} color="#0ea5e9" />
          <span style={{ fontSize: '0.82rem', fontWeight: 600, color: '#f8fafc' }}>
            24-Hour Continuous Recorded Stage Profile
          </span>
          <span
            style={{
              fontSize: '0.66rem',
              backgroundColor: 'rgba(16, 185, 129, 0.12)',
              color: '#10b981',
              padding: '2px 6px',
              borderRadius: 4,
              border: '1px solid rgba(16, 185, 129, 0.25)',
              fontWeight: 600,
            }}
          >
            Live Telemetry
          </span>
        </div>

        {/* View Mode Toggle */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, backgroundColor: 'rgba(255,255,255,0.04)', padding: 2, borderRadius: 6 }}>
          <button
            onClick={() => setViewMode('auto')}
            style={{
              padding: '3px 8px',
              fontSize: '0.7rem',
              fontWeight: 600,
              borderRadius: 4,
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 3,
              backgroundColor: viewMode === 'auto' ? '#0ea5e9' : 'transparent',
              color: viewMode === 'auto' ? '#ffffff' : '#94a3b8',
              transition: 'all 0.15s ease',
            }}
          >
            <ZoomIn size={11} /> Auto Focus
          </button>
          <button
            onClick={() => setViewMode('full')}
            style={{
              padding: '3px 8px',
              fontSize: '0.7rem',
              fontWeight: 600,
              borderRadius: 4,
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 3,
              backgroundColor: viewMode === 'full' ? '#0ea5e9' : 'transparent',
              color: viewMode === 'full' ? '#ffffff' : '#94a3b8',
              transition: 'all 0.15s ease',
            }}
          >
            <ZoomOut size={11} /> Danger Full Scale
          </button>
        </div>
      </div>

      {/* Observed Key Telemetry Bar */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 8,
          backgroundColor: 'rgba(0, 0, 0, 0.2)',
          padding: '8px 12px',
          borderRadius: 6,
          border: '1px solid var(--border-subtle)',
        }}
      >
        <div>
          <div style={{ fontSize: '0.66rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>
            Current Stage
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.92rem', fontWeight: 700, color: '#f8fafc' }}>
            {stats.current != null ? `${stats.current.toFixed(2)} ${unit}` : '—'}
          </div>
        </div>

        <div>
          <div style={{ fontSize: '0.66rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>
            24h Peak Stage
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.92rem', fontWeight: 700, color: '#38bdf8' }}>
            {stats.peak != null ? `${stats.peak.toFixed(2)} ${unit}` : '—'}
          </div>
          {stats.peakTime && (
            <div style={{ fontSize: '0.62rem', color: '#64748b' }}>at {stats.peakTime}</div>
          )}
        </div>

        <div>
          <div style={{ fontSize: '0.66rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>
            24h Min Stage
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.92rem', fontWeight: 700, color: '#94a3b8' }}>
            {stats.min != null ? `${stats.min.toFixed(2)} ${unit}` : '—'}
          </div>
        </div>

        <div>
          <div style={{ fontSize: '0.66rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>
            Gauge Rate of Change
          </div>
          <div style={{ fontSize: '0.78rem', fontWeight: 600, color: stats.trend.includes('Rising') ? '#f59e0b' : stats.trend.includes('Falling') ? '#10b981' : '#94a3b8' }}>
            {stats.trend}
          </div>
        </div>
      </div>

      {/* Main Chart */}
      <div style={{ width: '100%', height, position: 'relative' }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={observedPoints} margin={{ top: 12, right: 12, left: -16, bottom: 0 }}>
            <defs>
              <linearGradient id="observedAreaGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#0ea5e9" stopOpacity={0.35} />
                <stop offset="95%" stopColor="#0ea5e9" stopOpacity={0.0} />
              </linearGradient>
            </defs>

            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />

            <XAxis
              dataKey="time"
              stroke="#475569"
              tick={{ fontSize: 10, fill: '#64748b' }}
              minTickGap={35}
              axisLine={{ stroke: 'rgba(255,255,255,0.08)' }}
              tickLine={false}
            />

            <YAxis
              domain={yDomain}
              stroke="#475569"
              tick={{ fontSize: 10, fill: '#64748b', fontFamily: 'var(--font-mono)' }}
              tickFormatter={(v) => `${v}`}
              axisLine={{ stroke: 'rgba(255,255,255,0.08)' }}
              tickLine={false}
            />

            <Tooltip content={<CustomObservedTooltip unit={unit} />} />

            {/* Threshold Reference Lines */}
            {dangerLevel != null && dangerLevel > 0 && (
              <ReferenceLine
                y={dangerLevel}
                stroke="#ef4444"
                strokeDasharray="4 4"
                strokeWidth={1.5}
                label={{
                  value: `Danger (${Number(dangerLevel).toFixed(1)} ${unit})`,
                  position: 'insideTopRight',
                  fill: '#ef4444',
                  fontSize: 10,
                  fontWeight: 600,
                }}
              />
            )}

            {warningLevel != null && warningLevel > 0 && (
              <ReferenceLine
                y={warningLevel}
                stroke="#f59e0b"
                strokeDasharray="3 3"
                strokeWidth={1.2}
                label={{
                  value: `Warning (${Number(warningLevel).toFixed(1)} ${unit})`,
                  position: 'insideTopRight',
                  fill: '#f59e0b',
                  fontSize: 9,
                  fontWeight: 600,
                }}
              />
            )}

            {/* Observed Continuous Telemetry Area & Line */}
            <Area
              type="monotone"
              dataKey="observed"
              stroke="#0ea5e9"
              strokeWidth={2.5}
              fill="url(#observedAreaGrad)"
              isAnimationActive={false}
              dot={false}
              activeDot={{ r: 5, fill: '#38bdf8', stroke: '#080d1a', strokeWidth: 2 }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Legend & Threshold Clearance Banner */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.72rem', color: '#64748b', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 12, height: 3, backgroundColor: '#0ea5e9', borderRadius: 2 }} />
            <span style={{ color: '#cbd5e1' }}>Recorded Gauge Water Level</span>
          </span>
          {dangerLevel != null && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 10, height: 2, backgroundColor: '#ef4444' }} />
              <span style={{ color: '#f87171' }}>Danger Limit ({Number(dangerLevel).toFixed(1)} {unit})</span>
            </span>
          )}
        </div>

        {dangerLevel != null && stats.current != null && (
          <div style={{ color: '#10b981', fontWeight: 600 }}>
            Clearance to Danger: +{(Number(dangerLevel) - stats.current).toFixed(2)} {unit}
          </div>
        )}
      </div>
    </div>
  );
}
