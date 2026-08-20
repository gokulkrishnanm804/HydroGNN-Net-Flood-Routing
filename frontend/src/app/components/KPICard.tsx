'use client';
import { motion } from 'framer-motion';
import { useEffect, useState } from 'react';
import { TrendingUp, TrendingDown, Clock } from 'lucide-react';
import { STATUS_CONFIG, type Status } from '../data/mockData';
import styles from './KPICard.module.css';

// Tiny SVG sparkline
function Sparkline({ values, color }: { values: number[]; color: string }) {
  const w = 80, h = 32;
  const min = Math.min(...values), max = Math.max(...values);
  const norm = (v: number) => h - ((v - min) / (max - min || 1)) * h;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${norm(v)}`).join(' ');
  // area
  const area = `M 0,${norm(values[0])} L ${pts.split(' ').join(' L ')} L ${w},${h} L 0,${h} Z`;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ overflow: 'visible', flexShrink: 0 }}>
      <defs>
        <linearGradient id={`sg${color.replace('#','')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor={color} stopOpacity={0.35} />
          <stop offset="100%" stopColor={color} stopOpacity={0.02} />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#sg${color.replace('#','')})`} />
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
      {/* endpoint dot */}
      <circle
        cx={(values.length - 1) / (values.length - 1) * w}
        cy={norm(values[values.length - 1])}
        r={3} fill={color}
        style={{ filter: `drop-shadow(0 0 4px ${color})` }}
      />
    </svg>
  );
}

function useCountUp(target: number, decimals = 0, delay = 0, duration = 1600) {
  const [v, setV] = useState(0);
  useEffect(() => {
    const timer = setTimeout(() => {
      const start = performance.now();
      const step = (now: number) => {
        const t = Math.min((now - start) / duration, 1);
        const eased = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
        setV(parseFloat((eased * target).toFixed(decimals)));
        if (t < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    }, delay);
    return () => clearTimeout(timer);
  }, [target, decimals, delay, duration]);
  return v;
}

// Generate fake sparkline data from value + noise
function genSparkline(base: number, len = 12, volatility = 0.08) {
  let v = base * 0.85;
  return Array.from({ length: len }, () => {
    v = v * (1 + (Math.random() - 0.48) * volatility);
    return Math.max(0, v);
  }).concat([base]);
}

interface KPICardProps {
  title: string;
  value: number;
  unit?: string;
  decimals?: number;
  change?: number;
  changeLabel?: string;
  status?: string;
  icon?: React.ReactNode;
  accent?: string;
  delay?: number;
  subtitle?: string;
  lastUpdated?: string;
  sparkVolatility?: number;
}

export default function KPICard({
  title, value, unit, decimals = 0, change, changeLabel,
  status, icon, accent = '#22d3ee', delay = 0, subtitle,
  lastUpdated = '2 min ago', sparkVolatility = 0.10,
}: KPICardProps) {
  const displayed = useCountUp(value, decimals, delay * 120);
  const sc = status ? STATUS_CONFIG[status] : null;
  const sparkData = genSparkline(value, 14, sparkVolatility);

  return (
    <motion.div
      className={`${styles.card} glass-card`}
      initial={{ opacity: 0, y: 20, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.5, delay: delay * 0.1, ease: [0.34, 1.04, 0.64, 1] }}
      whileHover={{ y: -5, transition: { duration: 0.2, ease: 'easeOut' } }}
    >
      {/* Ambient glow on hover */}
      <div className={styles.hoverGlow} style={{ background: `radial-gradient(circle at 30% 40%, ${accent}18, transparent 65%)` }} />

      {/* Gradient border shimmer */}
      <div className={styles.borderShimmer} style={{ background: `linear-gradient(135deg, ${accent}35, transparent 50%)` }} />

      {/* Header row */}
      <div className={styles.header}>
        <motion.div
          className={styles.iconWrap}
          style={{ background: `${accent}14`, border: `1px solid ${accent}28` }}
          whileHover={{ scale: 1.12, rotate: 8 }}
          transition={{ type: 'spring', stiffness: 350 }}
        >
          {icon}
        </motion.div>

        <div className={styles.headerRight}>
          {sc && (
            <span className={`badge badge-${status}`} style={{ fontSize: '0.6rem', padding: '2px 7px' }}>
              <span className={`status-dot status-${status}`} style={{ width: 5, height: 5 }} />
              {sc.label}
            </span>
          )}
        </div>
      </div>

      {/* Value */}
      <div className={styles.valueRow}>
        <motion.span
          className={styles.value}
          style={{ color: accent }}
        >
          {displayed.toLocaleString('en-IN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}
        </motion.span>
        {unit && <span className={styles.unit}>{unit}</span>}
      </div>

      {/* Title + subtitle */}
      <div className={styles.titleRow}>{title}</div>
      {subtitle && <div className={styles.subtitle}>{subtitle}</div>}

      {/* Sparkline + change */}
      <div className={styles.footer}>
        <div className={styles.footerLeft}>
          {change !== undefined && (
            <span className={`kpi-change ${change >= 0 ? 'up' : 'down'}`} style={{ fontSize: '0.78rem' }}>
              {change >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
              {Math.abs(change)}%
            </span>
          )}
          {changeLabel && (
            <span style={{ fontSize: '0.68rem', color: 'rgba(255,255,255,0.28)' }}>{changeLabel}</span>
          )}
        </div>
        <div className={styles.sparkWrap}>
          <Sparkline values={sparkData} color={accent} />
        </div>
      </div>

      {/* Last updated */}
      <div className={styles.lastUpdated}>
        <Clock size={10} style={{ opacity: 0.4 }} />
        <span>{lastUpdated}</span>
      </div>
    </motion.div>
  );
}
