'use client';
import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard, Map, TrendingUp, Radio, Brain,
  Bell, Database, FileText, ChevronLeft, Waves,
  Activity, Settings, HelpCircle, GitBranch
} from 'lucide-react';
import styles from './Sidebar.module.css';
import { api } from '../../services/api';

const NAV_GROUPS = [
  {
    label: 'MONITORING',
    items: [
      { href: '/',         icon: LayoutDashboard, label: 'Dashboard',     desc: 'Real-time basin overview',          badge: null,  badgeVariant: null },
      { href: '/map',      icon: Map,             label: 'Basin Map',     desc: 'Spatial river & station view',      badge: 'LIVE',badgeVariant: 'info' },
      { href: '/forecast', icon: TrendingUp,      label: 'Forecast',      desc: '6–24h water-level prediction',      badge: '24h', badgeVariant: 'safe' },
      { href: '/stations', icon: Radio,           label: 'Stations',      desc: 'Station-level monitoring',          badge: '8',   badgeVariant: null },
      { href: '/routing',  icon: GitBranch,       label: 'Flood Routing', desc: 'River flow propagation',             badge: 'NEW', badgeVariant: 'warning' },
    ],
  },
  {
    label: 'INTELLIGENCE',
    items: [
      { href: '/model',    icon: Brain,    label: 'AI Model',      desc: 'Experiment 9 model & performance',  badge: null, badgeVariant: null },
      { href: '/alerts',   icon: Bell,     label: 'Alerts',        desc: 'Flood warnings & events',            badge: '0',  badgeVariant: 'safe' },
      { href: '/pipeline', icon: Database, label: 'Data Pipeline', desc: 'Data sources & freshness',           badge: null, badgeVariant: null },
      { href: '/reports',  icon: FileText, label: 'Reports',       desc: 'Evaluation & system reports',        badge: null, badgeVariant: null },
    ],
  },
];

const BOTTOM_ITEMS = [
  { href: '/settings', icon: Settings,   label: 'Settings', desc: 'System configuration' },
  { href: '/help',     icon: HelpCircle, label: 'Help',     desc: 'System guide & terminology' },
];

const BADGE_COLORS: Record<string, { bg: string; color: string; border: string }> = {
  info:    { bg: 'rgba(34,211,238,0.15)',   color: '#22d3ee',  border: 'rgba(34,211,238,0.25)' },
  safe:    { bg: 'rgba(52,211,153,0.15)',   color: '#34d399',  border: 'rgba(52,211,153,0.25)' },
  warning: { bg: 'rgba(251,146,60,0.15)',   color: '#fb923c',  border: 'rgba(251,146,60,0.25)' },
  danger:  { bg: 'rgba(251,113,133,0.15)',  color: '#fb7185',  border: 'rgba(251,113,133,0.25)' },
};

export default function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const pathname = usePathname();
  const [alertCount, setAlertCount] = useState<number | null>(null);

  useEffect(() => {
    let isMounted = true;
    const fetchAlertCount = async () => {
      try {
        await api.login();
        const logs = await api.getAlerts();
        if (isMounted && Array.isArray(logs)) {
          setAlertCount(logs.length);
        }
      } catch (err) {
        if (isMounted) setAlertCount(0);
      }
    };
    fetchAlertCount();
    const interval = setInterval(fetchAlertCount, 15000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <motion.aside
      className={styles.sidebar}
      animate={{ width: collapsed ? 72 : 264 }}
      transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
    >
      {/* Top accent line */}
      <div className={styles.accentLine} />

      {/* Logo */}
      <div className={styles.logo}>
        <motion.div
          className={styles.logoIcon}
          whileHover={{ scale: 1.08, rotate: 5 }}
          whileTap={{ scale: 0.92 }}
          transition={{ type: 'spring', stiffness: 400 }}
        >
          <Waves size={20} color="#22d3ee" />
          {/* Animated glow ring */}
          <div className={styles.logoGlow} />
        </motion.div>

        <AnimatePresence>
          {!collapsed && (
            <motion.div
              initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.22, ease: 'easeOut' }}
              className={styles.logoText}
            >
              <span className={styles.logoTitle}>HydroGNN</span>
              <span className={styles.logoSub}>Gov. Decision Support</span>
            </motion.div>
          )}
        </AnimatePresence>

        <motion.button
          className={styles.collapseBtn}
          onClick={onToggle}
          whileHover={{ scale: 1.15, backgroundColor: 'rgba(34,211,238,0.12)' }}
          whileTap={{ scale: 0.88 }}
          animate={{ rotate: collapsed ? 180 : 0 }}
          transition={{ duration: 0.3 }}
        >
          <ChevronLeft size={14} />
        </motion.button>
      </div>

      {/* System status chip */}
      <AnimatePresence>
        {!collapsed && (
          <motion.div
            className={styles.statusChip}
            initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.2 }}
          >
            <div className={styles.statusDotLive} />
            <span className={styles.statusLabel}>SYSTEM OPERATIONAL</span>
            <span className={styles.statusVersion}>v2.4.1</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Navigation */}
      <nav className={styles.nav}>
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className={styles.navGroup}>
            <AnimatePresence>
              {!collapsed && (
                <motion.p
                  className={styles.groupLabel}
                  initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                  transition={{ duration: 0.15 }}
                >
                  {group.label}
                </motion.p>
              )}
            </AnimatePresence>

            {group.items.map((item) => {
              const active = pathname === item.href;
              const isAlertsItem = item.href === '/alerts';
              const displayBadge = isAlertsItem
                ? (alertCount !== null ? String(alertCount) : '0')
                : item.badge;
              const displayVariant = isAlertsItem
                ? ((alertCount || 0) > 0 ? 'danger' : 'safe')
                : item.badgeVariant;
              const badgeStyle = displayVariant ? BADGE_COLORS[displayVariant] : null;
              const tooltipText = `${item.label} — ${item.desc}`;
              return (
                <Link key={item.href} href={item.href} style={{ textDecoration: 'none' }}>
                  <motion.div
                    className={`${styles.navItem} ${active ? styles.navItemActive : ''}`}
                    whileHover={{ x: collapsed ? 0 : 3 }}
                    whileTap={{ scale: 0.97 }}
                    transition={{ duration: 0.12 }}
                    title={collapsed ? tooltipText : undefined}
                    data-tooltip={collapsed ? tooltipText : undefined}
                  >
                    {active && (
                      <motion.div
                        className={styles.activeBar}
                        layoutId="activeNavBar"
                        transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
                      />
                    )}

                    {active && (
                      <motion.div className={styles.activeGlow} layoutId="activeGlow" />
                    )}

                    <motion.div
                      className={styles.navIcon}
                      animate={{ color: active ? '#22d3ee' : 'rgba(255,255,255,0.42)' }}
                      transition={{ duration: 0.15 }}
                    >
                      <item.icon size={17} strokeWidth={active ? 2.2 : 1.8} />
                    </motion.div>

                    <AnimatePresence>
                      {!collapsed && (
                        <motion.div
                          className={styles.navTextCol}
                          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                          transition={{ duration: 0.15 }}
                        >
                          <span
                            className={styles.navLabel}
                            style={{ color: active ? 'rgba(255,255,255,0.98)' : 'rgba(255,255,255,0.7)' }}
                          >
                            {item.label}
                          </span>
                          <span className={styles.navDesc}>
                            {item.desc}
                          </span>
                        </motion.div>
                      )}
                    </AnimatePresence>

                    <AnimatePresence>
                      {!collapsed && displayBadge && badgeStyle && (
                        <motion.span
                          className={styles.navBadge}
                          style={{ background: badgeStyle.bg, color: badgeStyle.color, border: `1px solid ${badgeStyle.border}` }}
                          initial={{ opacity: 0, scale: 0.7 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}
                        >
                          {displayBadge}
                        </motion.span>
                      )}
                      {!collapsed && displayBadge && !badgeStyle && (
                        <motion.span
                          className={styles.navBadge}
                          style={{ background: 'rgba(255,255,255,0.06)', color: 'rgba(255,255,255,0.4)', border: '1px solid rgba(255,255,255,0.08)' }}
                          initial={{ opacity: 0, scale: 0.7 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}
                        >
                          {displayBadge}
                        </motion.span>
                      )}
                    </AnimatePresence>
                  </motion.div>
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      {/* Bottom section */}
      <div className={styles.bottom}>
        <div className={styles.dividerLine} />

        {BOTTOM_ITEMS.map(item => (
          <Link key={item.href} href={item.href} style={{ textDecoration: 'none' }}>
            <motion.div
              className={styles.navItem}
              whileHover={{ backgroundColor: 'rgba(255,255,255,0.04)' }}
              title={collapsed ? `${item.label} — ${item.desc}` : undefined}
              data-tooltip={collapsed ? `${item.label} — ${item.desc}` : undefined}
            >
              <div className={styles.navIcon} style={{ color: 'rgba(255,255,255,0.28)' }}>
                <item.icon size={16} strokeWidth={1.7} />
              </div>
              <AnimatePresence>
                {!collapsed && (
                  <motion.div
                    className={styles.navTextCol}
                    initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                  >
                    <span className={styles.navLabel} style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.82rem' }}>
                      {item.label}
                    </span>
                    <span className={styles.navDesc}>
                      {item.desc}
                    </span>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          </Link>
        ))}

        {/* User card */}
        <AnimatePresence>
          {!collapsed && (
            <motion.div className={styles.userCard}
              initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 4 }}
              transition={{ duration: 0.2 }}
            >
              <div className={styles.avatar}>GK</div>
              <div className={styles.userInfo}>
                <div className={styles.userName}>Gokul K.</div>
                <div className={styles.userRole}>Research Engineer</div>
              </div>
              <div className={styles.userOnline}>
                <Activity size={12} color="#34d399" />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.aside>
  );
}
