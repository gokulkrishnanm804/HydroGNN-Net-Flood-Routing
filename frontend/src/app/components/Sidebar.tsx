'use client';
import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  Radio,
  TrendingUp,
  GitBranch,
  Bell,
  Brain,
  FileText,
  Activity,
  ChevronLeft,
  ChevronRight,
  Waves,
} from 'lucide-react';
import { api } from '../../services/api';

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

const NAV_ITEMS = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/stations', label: 'Stations', icon: Radio },
  { href: '/forecast', label: 'Forecast', icon: TrendingUp },
  { href: '/routing', label: 'Flood Routing', icon: GitBranch },
  { href: '/alerts', label: 'Alerts', icon: Bell, badge: true },
  { href: '/model', label: 'Model', icon: Brain },
  { href: '/reports', label: 'Reports', icon: FileText },
  { href: '/diagnostics', label: 'System / Diagnostics', icon: Activity },
];

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const pathname = usePathname();
  const [activeAlertCount, setActiveAlertCount] = useState<number>(0);

  useEffect(() => {
    let isMounted = true;
    const loadAlerts = async () => {
      try {
        await api.login();
        const alerts = await api.getAlerts();
        if (isMounted && Array.isArray(alerts)) {
          setActiveAlertCount(alerts.length);
        }
      } catch {
        // Silently handle
      }
    };
    loadAlerts();
    const interval = setInterval(loadAlerts, 30000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <aside
      style={{
        width: collapsed ? 68 : 240,
        backgroundColor: '#0a1020',
        borderRight: '1px solid rgba(255, 255, 255, 0.08)',
        height: '100vh',
        position: 'fixed',
        top: 0,
        left: 0,
        zIndex: 50,
        display: 'flex',
        flexDirection: 'column',
        transition: 'width 0.2s ease',
        userSelect: 'none',
      }}
    >
      {/* Brand Header */}
      <div
        style={{
          height: 58,
          display: 'flex',
          alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'space-between',
          padding: collapsed ? '0' : '0 16px',
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
        }}
      >
        <Link
          href="/"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            textDecoration: 'none',
            color: '#f8fafc',
          }}
        >
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 6,
              backgroundColor: '#0ea5e9',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <Waves size={18} color="#ffffff" />
          </div>
          {!collapsed && (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ fontWeight: 700, fontSize: '0.92rem', letterSpacing: '0.02em', lineHeight: 1.2 }}>
                HydroGNN-Net
              </span>
              <span style={{ fontSize: '0.66rem', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Cauvery Flood Routing
              </span>
            </div>
          )}
        </Link>
      </div>

      {/* Navigation Links */}
      <nav
        style={{
          flex: 1,
          padding: '12px 8px',
          display: 'flex',
          flexDirection: 'column',
          gap: 3,
          overflowY: 'auto',
        }}
      >
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href));

          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: collapsed ? '9px 0' : '8px 12px',
                justifyContent: collapsed ? 'center' : 'flex-start',
                borderRadius: 6,
                textDecoration: 'none',
                color: isActive ? '#f8fafc' : '#94a3b8',
                backgroundColor: isActive ? 'rgba(14, 165, 233, 0.14)' : 'transparent',
                border: `1px solid ${isActive ? 'rgba(14, 165, 233, 0.28)' : 'transparent'}`,
                fontWeight: isActive ? 600 : 400,
                fontSize: '0.82rem',
                transition: 'all 0.12s ease',
              }}
            >
              <Icon size={17} color={isActive ? '#38bdf8' : '#94a3b8'} style={{ flexShrink: 0 }} />
              {!collapsed && <span style={{ flex: 1 }}>{item.label}</span>}
              {!collapsed && item.badge && activeAlertCount > 0 && (
                <span
                  style={{
                    backgroundColor: '#ef4444',
                    color: '#ffffff',
                    fontSize: '0.65rem',
                    fontWeight: 700,
                    padding: '1px 6px',
                    borderRadius: 9999,
                  }}
                >
                  {activeAlertCount}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Collapse Footer */}
      <div
        style={{
          padding: 8,
          borderTop: '1px solid rgba(255, 255, 255, 0.08)',
          display: 'flex',
          justifyContent: collapsed ? 'center' : 'flex-end',
        }}
      >
        <button
          onClick={onToggle}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          style={{
            background: 'rgba(255, 255, 255, 0.04)',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            color: '#94a3b8',
            width: 28,
            height: 28,
            borderRadius: 4,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {collapsed ? <ChevronRight size={15} /> : <ChevronLeft size={15} />}
        </button>
      </div>
    </aside>
  );
}
