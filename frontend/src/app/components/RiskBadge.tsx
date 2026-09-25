'use client';
import React from 'react';

export type RiskLevel = 'Safe' | 'Low Risk' | 'Moderate Risk' | 'High Risk' | 'Severe Flood' | string;

interface RiskBadgeProps {
  level: RiskLevel;
  showDot?: boolean;
  className?: string;
  size?: 'sm' | 'md';
}

export function getRiskVariant(level: string): {
  variant: 'safe' | 'low' | 'warning' | 'danger';
  label: string;
  color: string;
} {
  const normalized = (level || '').toLowerCase().trim();
  if (normalized.includes('severe') || normalized.includes('danger') || normalized.includes('critical') || normalized.includes('high')) {
    return { variant: 'danger', label: level || 'High Risk', color: '#ef4444' };
  }
  if (normalized.includes('moderate') || normalized.includes('warn') || normalized.includes('elevated')) {
    return { variant: 'warning', label: level || 'Warning', color: '#f59e0b' };
  }
  if (normalized.includes('low') || normalized.includes('alert')) {
    return { variant: 'low', label: level || 'Low Risk', color: '#06b6d4' };
  }
  return { variant: 'safe', label: level || 'Safe', color: '#10b981' };
}

export default function RiskBadge({ level, showDot = true, className = '', size = 'md' }: RiskBadgeProps) {
  const { variant, label, color } = getRiskVariant(level);

  const padding = size === 'sm' ? '1px 6px' : '2px 8px';
  const fontSize = size === 'sm' ? '0.68rem' : '0.72rem';

  return (
    <span
      className={`badge badge-${variant} ${className}`}
      style={{
        padding,
        fontSize,
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        borderRadius: 4,
        fontWeight: 600,
        letterSpacing: '0.02em',
      }}
    >
      {showDot && (
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            backgroundColor: color,
            display: 'inline-block',
          }}
        />
      )}
      {label}
    </span>
  );
}
