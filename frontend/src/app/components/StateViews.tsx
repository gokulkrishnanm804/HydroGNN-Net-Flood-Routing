'use client';
import React from 'react';
import { AlertTriangle, RefreshCw, Inbox } from 'lucide-react';

export function LoadingSkeleton({ rows = 4, height = 80 }: { rows?: number; height?: number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, width: '100%', padding: '16px 0' }}>
      <div className="skeleton" style={{ height: 38, width: '40%', marginBottom: 8 }} />
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height, width: '100%', borderRadius: 8 }} />
      ))}
    </div>
  );
}

export function ErrorBanner({
  title = 'Unable to Load Live Data',
  message = 'Failed to connect to the flood routing API service. Ensure the FastAPI backend is running.',
  onRetry,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '48px 24px',
        textAlign: 'center',
        background: 'rgba(239, 68, 68, 0.05)',
        border: '1px solid rgba(239, 68, 68, 0.2)',
        borderRadius: 8,
        margin: '20px 0',
      }}
    >
      <AlertTriangle size={36} color="#ef4444" style={{ marginBottom: 12 }} />
      <h3 style={{ fontSize: '1.05rem', fontWeight: 600, color: '#f8fafc', marginBottom: 6 }}>
        {title}
      </h3>
      <p style={{ fontSize: '0.84rem', color: '#94a3b8', maxWidth: 440, lineHeight: 1.5, marginBottom: 16 }}>
        {message}
      </p>
      {onRetry && (
        <button className="btn btn-secondary btn-sm" onClick={onRetry}>
          <RefreshCw size={13} />
          Retry Connection
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  title = 'No Records Found',
  message = 'There is currently no data to display for this selection.',
  icon: Icon = Inbox,
}: {
  title?: string;
  message?: string;
  icon?: any;
}) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '48px 24px',
        textAlign: 'center',
        background: 'rgba(255, 255, 255, 0.02)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 8,
        color: '#64748b',
      }}
    >
      <Icon size={36} color="#64748b" style={{ marginBottom: 12 }} />
      <h3 style={{ fontSize: '0.95rem', fontWeight: 600, color: '#e2e8f0', marginBottom: 4 }}>
        {title}
      </h3>
      <p style={{ fontSize: '0.82rem', color: '#94a3b8', maxWidth: 360 }}>
        {message}
      </p>
    </div>
  );
}
