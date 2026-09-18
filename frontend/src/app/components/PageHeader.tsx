'use client';
import { motion } from 'framer-motion';
import { Info } from 'lucide-react';

interface Badge {
  label: string;
  variant?: 'safe' | 'info' | 'warning' | 'danger';
}

interface PageHeaderProps {
  title: string;
  subtitle: string;
  purpose: string;
  badges?: Badge[];
  instruction?: string;
}

const BADGE_STYLES: Record<string, { bg: string; color: string; border: string }> = {
  safe:    { bg: 'rgba(52,211,153,0.12)',  color: '#34d399', border: 'rgba(52,211,153,0.25)' },
  info:    { bg: 'rgba(34,211,238,0.12)',  color: '#22d3ee', border: 'rgba(34,211,238,0.25)' },
  warning: { bg: 'rgba(251,146,60,0.12)', color: '#fb923c', border: 'rgba(251,146,60,0.25)' },
  danger:  { bg: 'rgba(251,113,133,0.12)', color: '#fb7185', border: 'rgba(251,113,133,0.25)' },
};

export default function PageHeader({ title, subtitle, purpose, badges, instruction }: PageHeaderProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      style={{
        marginBottom: 20,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      {/* Title + Subtitle + Optional Badges */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{
            fontSize: '1.45rem',
            fontWeight: 800,
            color: '#f8fafc',
            margin: 0,
            letterSpacing: '-0.025em',
            fontFamily: 'var(--font-display, "Inter", sans-serif)'
          }}>
            {title}
          </h1>
          <p style={{
            fontSize: '0.82rem',
            color: 'rgba(255,255,255,0.5)',
            margin: '4px 0 0',
            lineHeight: 1.4
          }}>
            {subtitle}
          </p>
        </div>

        {badges && badges.length > 0 && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            {badges.map((b, idx) => {
              const style = BADGE_STYLES[b.variant || 'info'];
              return (
                <span
                  key={idx}
                  style={{
                    background: style.bg,
                    color: style.color,
                    border: `1px solid ${style.border}`,
                    borderRadius: 8,
                    fontSize: '0.68rem',
                    fontWeight: 700,
                    padding: '4px 10px',
                    letterSpacing: '0.04em',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6
                  }}
                >
                  <span style={{ width: 5, height: 5, borderRadius: '50%', background: style.color }} />
                  {b.label}
                </span>
              );
            })}
          </div>
        )}
      </div>

      {/* Purpose Strip */}
      <div style={{
        background: 'rgba(10, 26, 56, 0.65)',
        border: '1px solid rgba(34, 211, 238, 0.16)',
        borderRadius: 10,
        padding: '9px 14px',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        boxShadow: '0 2px 12px rgba(0,0,0,0.2)'
      }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 5,
          padding: '2px 7px',
          background: 'rgba(34,211,238,0.12)',
          borderRadius: 6,
          border: '1px solid rgba(34,211,238,0.22)',
          flexShrink: 0
        }}>
          <Info size={12} color="#22d3ee" />
          <span style={{
            fontSize: '0.64rem',
            fontWeight: 800,
            color: '#22d3ee',
            letterSpacing: '0.08em',
            textTransform: 'uppercase'
          }}>
            PURPOSE
          </span>
        </div>
        <span style={{
          fontSize: '0.8rem',
          color: 'rgba(255,255,255,0.75)',
          lineHeight: 1.4,
          fontWeight: 450
        }}>
          {purpose}
        </span>
        {instruction && (
          <span style={{
            marginLeft: 'auto',
            fontSize: '0.74rem',
            color: '#34d399',
            fontStyle: 'italic',
            whiteSpace: 'nowrap',
            flexShrink: 0
          }}>
            {instruction}
          </span>
        )}
      </div>
    </motion.div>
  );
}
