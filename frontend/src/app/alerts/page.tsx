'use client';
import React, { useState, useEffect, useMemo } from 'react';
import AppLayout from '../AppLayout';
import RiskBadge from '../components/RiskBadge';
import { LoadingSkeleton, ErrorBanner, EmptyState } from '../components/StateViews';
import { api } from '../../services/api';
import {
  Bell,
  AlertTriangle,
  CheckCircle,
  ShieldCheck,
  Clock,
  MapPin,
  HelpCircle,
} from 'lucide-react';

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState<'active' | 'resolved'>('active');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [hasError, setHasError] = useState<boolean>(false);

  const fetchAlerts = async () => {
    try {
      setIsLoading(true);
      setHasError(false);
      await api.login();
      const logs = await api.getAlerts();

      const formatted = (logs || []).map((l: any, i: number) => ({
        id: l.id || i + 1,
        station: l.station_name || 'Cauvery Reach',
        severity: l.severity || 'WARNING',
        current_level: l.level_m || null,
        trigger: l.event_type || l.message || 'Operational threshold exceeded',
        time: l.timestamp || 'Recent',
        active: l.active !== undefined ? l.active : true,
        advisory:
          l.advisory ||
          (l.severity === 'CRITICAL'
            ? 'Issue immediate flood bulletin and prepare low-lying reach evacuations.'
            : 'Maintain intensified hourly stage monitoring and alert local reservoir authorities.'),
      }));

      setAlerts(formatted);
    } catch (err) {
      console.error('Failed to load alerts:', err);
      setHasError(true);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchAlerts();
  }, []);

  const activeAlerts = useMemo(() => {
    return alerts
      .filter((a) => a.active)
      .sort((a, b) => (a.severity === 'CRITICAL' ? -1 : 1));
  }, [alerts]);

  const resolvedAlerts = useMemo(() => {
    return alerts.filter((a) => !a.active);
  }, [alerts]);

  if (isLoading) {
    return (
      <AppLayout>
        <LoadingSkeleton rows={4} height={100} />
      </AppLayout>
    );
  }

  if (hasError) {
    return (
      <AppLayout>
        <ErrorBanner onRetry={fetchAlerts} />
      </AppLayout>
    );
  }

  const currentList = activeTab === 'active' ? activeAlerts : resolvedAlerts;

  return (
    <AppLayout>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        {/* Top Header & Tab Toggle */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <h2 style={{ fontSize: '1.2rem', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
              Actionable Flood Hazard Warnings
            </h2>
            <p style={{ fontSize: '0.8rem', color: '#94a3b8', margin: '2px 0 0' }}>
              Real-time threshold exceedance alerts and disaster management advisories
            </p>
          </div>

          {/* Active vs Resolved Tabs */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button
              onClick={() => setActiveTab('active')}
              className={`btn btn-sm ${activeTab === 'active' ? 'btn-primary' : 'btn-secondary'}`}
            >
              Active Warnings ({activeAlerts.length})
            </button>
            <button
              onClick={() => setActiveTab('resolved')}
              className={`btn btn-sm ${activeTab === 'resolved' ? 'btn-primary' : 'btn-secondary'}`}
            >
              Resolved History ({resolvedAlerts.length})
            </button>
          </div>
        </div>

        {/* Alerts List */}
        {currentList.length === 0 ? (
          <EmptyState
            title={activeTab === 'active' ? 'No Active Flood Alerts' : 'No Resolved Alert Records'}
            message={
              activeTab === 'active'
                ? 'All monitored Cauvery Basin gauges are operating within normal design safety thresholds.'
                : 'No historical alert resolutions logged in the current operational cycle.'
            }
            icon={ShieldCheck}
          />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {currentList.map((alert) => {
              const isCritical = alert.severity === 'CRITICAL' || alert.severity === 'Severe Flood';

              return (
                <div
                  key={alert.id}
                  className="card"
                  style={{
                    borderLeft: `4px solid ${isCritical ? '#ef4444' : '#f59e0b'}`,
                    padding: '16px 20px',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                      marginBottom: 8,
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div
                        style={{
                          width: 32,
                          height: 32,
                          borderRadius: 6,
                          backgroundColor: isCritical
                            ? 'rgba(239, 68, 68, 0.12)'
                            : 'rgba(245, 158, 11, 0.12)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          color: isCritical ? '#ef4444' : '#f59e0b',
                        }}
                      >
                        <AlertTriangle size={16} />
                      </div>

                      <div>
                        <h4 style={{ fontSize: '0.94rem', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
                          {alert.station}
                        </h4>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: '0.72rem', color: '#94a3b8', marginTop: 2 }}>
                          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <Clock size={11} /> {alert.time}
                          </span>
                          {alert.current_level && (
                            <span>
                              Stage:{' '}
                              <strong style={{ color: '#f8fafc' }}>
                                {Number(alert.current_level).toFixed(2)} ft
                              </strong>
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    <RiskBadge level={alert.severity} />
                  </div>

                  {/* Trigger Reason */}
                  <div style={{ fontSize: '0.82rem', color: '#e2e8f0', margin: '8px 0 10px', paddingLeft: 42 }}>
                    <strong>Trigger Condition:</strong> {alert.trigger}
                  </div>

                  {/* Recommended Action / Advisory */}
                  <div
                    style={{
                      marginLeft: 42,
                      padding: '8px 12px',
                      backgroundColor: 'var(--bg-surface)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: 6,
                      fontSize: '0.76rem',
                      color: '#94a3b8',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                    }}
                  >
                    <span style={{ color: '#0ea5e9', fontWeight: 600 }}>Recommended Action:</span>
                    <span>{alert.advisory}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </AppLayout>
  );
}
