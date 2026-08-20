'use client';
import { motion, AnimatePresence } from 'framer-motion';
import { useState, useEffect } from 'react';
import { Bell, Search, RefreshCw, Wifi, ChevronDown, X } from 'lucide-react';
import styles from './TopBar.module.css';
import { api } from '../../services/api';

const BREADCRUMBS: Record<string, { label: string; sub: string }> = {
  '/':         { label: 'Dashboard',      sub: 'Overview · Real-time monitoring' },
  '/map':      { label: 'Basin Map',      sub: 'Cauvery Basin · Interactive monitoring' },
  '/forecast': { label: 'Flood Forecast', sub: 'AI multi-horizon prediction · GNN ensemble' },
  '/stations': { label: 'Stations',       sub: '8 active CWC gauging stations' },
  '/routing':  { label: 'Flood Routing',  sub: 'Downstream propagation · Animated path' },
  '/model':    { label: 'AI Model',       sub: 'HydroGNN-Net v2.4 · GRU → GATv2 → GraphSAGE' },
  '/alerts':   { label: 'Alert Center',   sub: 'Warning management · Active incidents' },
  '/pipeline': { label: 'Data Pipeline',  sub: 'Dataset status · Preprocessing readiness' },
  '/reports':  { label: 'Reports',        sub: 'Research-grade analysis · Export ready' },
};

export default function TopBar() {
  const [mounted, setMounted] = useState(false);
  const [time, setTime] = useState<Date | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [path, setPath] = useState('/');
  const [showAlerts, setShowAlerts] = useState(false);
  const [searchFocused, setSearchFocused] = useState(false);
  const [activeAlerts, setActiveAlerts] = useState<any[]>([]);

  useEffect(() => {
    setMounted(true);
    setTime(new Date());
    const t = setInterval(() => setTime(new Date()), 1000);
    if (typeof window !== 'undefined') setPath(window.location.pathname);
    
    let isMounted = true;
    const fetchLiveAlerts = async () => {
      try {
        await api.login();
        const logs = await api.getAlerts();
        if (isMounted && Array.isArray(logs)) {
          setActiveAlerts(logs);
        }
      } catch (err) {
        if (isMounted) setActiveAlerts([]);
      }
    };
    fetchLiveAlerts();
    const alertInterval = setInterval(fetchLiveAlerts, 15000);

    return () => {
      clearInterval(t);
      clearInterval(alertInterval);
      isMounted = false;
    };
  }, []);

  const meta = BREADCRUMBS[path] ?? BREADCRUMBS['/'];

  const handleSync = () => {
    setSyncing(true);
    setTimeout(() => setSyncing(false), 2200);
  };

  return (
    <motion.header
      className={styles.topbar}
      initial={{ y: -64, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.4, ease: [0.4, 0, 0.2, 1] }}
    >
      {/* Left — page info */}
      <div className={styles.left}>
        <div className={styles.pageInfo}>
          <div className={styles.pageName}>{meta.label}</div>
          <div className={styles.pageSub}>{meta.sub}</div>
        </div>

        {/* Live indicator */}
        <motion.div className={styles.livePill} whileHover={{ scale: 1.04 }}>
          <div className={styles.liveDot} />
          <span>LIVE</span>
        </motion.div>
      </div>

      {/* Right — controls */}
      <div className={styles.right}>

        {/* Search */}
        <motion.div
          className={styles.searchWrap}
          animate={{ width: searchFocused ? 260 : 200 }}
          transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
        >
          <Search size={13} style={{ flexShrink: 0, color: searchFocused ? '#22d3ee' : 'rgba(255,255,255,0.25)' }} />
          <input
            className={styles.searchInput}
            placeholder="Search stations, events…"
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setSearchFocused(false)}
          />
          <AnimatePresence>
            {searchFocused && (
              <motion.kbd initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                className={styles.kbdHint}
              >ESC</motion.kbd>
            )}
          </AnimatePresence>
        </motion.div>

        {/* Sync */}
        <motion.button
          className={styles.iconBtn}
          onClick={handleSync}
          whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.88 }}
          data-tooltip="Sync all feeds"
        >
          <motion.div
            animate={{ rotate: syncing ? 360 : 0 }}
            transition={{ duration: 0.9, repeat: syncing ? Infinity : 0, ease: 'linear' }}
          >
            <RefreshCw size={14} color={syncing ? '#22d3ee' : 'rgba(255,255,255,0.45)'} />
          </motion.div>
        </motion.button>

        {/* Alerts bell */}
        <div className={styles.alertWrap}>
          <motion.button
            className={styles.iconBtn}
            onClick={() => setShowAlerts(s => !s)}
            whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.88 }}
          >
            <motion.div animate={{ rotate: showAlerts ? [0, -12, 12, -8, 8, 0] : 0 }} transition={{ duration: 0.5 }}>
              <Bell size={14} color={showAlerts ? '#fb7185' : 'rgba(255,255,255,0.45)'} />
            </motion.div>
            <span className={styles.alertBadge}>{activeAlerts.length}</span>
          </motion.button>

          <AnimatePresence>
            {showAlerts && (
              <motion.div
                className={styles.alertDropdown}
                initial={{ opacity: 0, y: -8, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -8, scale: 0.95 }}
                transition={{ duration: 0.18 }}
              >
                <div className={styles.dropdownHeader}>
                  <span style={{ fontWeight: 700, fontSize: '0.85rem' }}>Active Alerts ({activeAlerts.length})</span>
                  <motion.button whileHover={{ scale: 1.1 }} onClick={() => setShowAlerts(false)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.4)' }}
                  ><X size={14} /></motion.button>
                </div>
                {activeAlerts.length > 0 ? (
                  activeAlerts.slice(0, 5).map((a, idx) => {
                    const status = (a.severity || 'WARNING').toLowerCase() === 'critical' ? 'danger' : (a.severity || 'WARNING').toLowerCase() === 'warning' ? 'warning' : 'alert';
                    return (
                      <div key={a.id || idx} className={styles.dropdownItem}>
                        <span className={`status-dot status-${status}`} style={{ width: 6, height: 6, flexShrink: 0 }} />
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'rgba(255,255,255,0.9)' }}>{a.station_name || 'System'}</div>
                          <div style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.45)' }}>{a.message}</div>
                        </div>
                        <span style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.28)', whiteSpace: 'nowrap' }}>{a.timestamp ? a.timestamp.split(' ')[1] : 'Live'}</span>
                      </div>
                    );
                  })
                ) : (
                  <div style={{ padding: '16px 20px', textAlign: 'center', fontSize: '0.78rem', color: 'rgba(255,255,255,0.45)' }}>
                    No active alerts to display
                  </div>
                )}
                <a href="/alerts" style={{ display: 'block', textAlign: 'center', padding: '10px', fontSize: '0.75rem', color: '#22d3ee', textDecoration: 'none', borderTop: '1px solid rgba(255,255,255,0.06)', fontWeight: 500 }}>
                  View all alerts →
                </a>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Connection status */}
        <motion.div className={styles.connPill} whileHover={{ scale: 1.03 }}>
          <Wifi size={12} color="#34d399" />
          <span>Connected</span>
        </motion.div>

        {/* Clock */}
        <div className={styles.clock}>
          <div className={styles.clockTime}>
            {mounted && time
              ? time.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
              : '--:--:--'}
          </div>
          <div className={styles.clockDate}>
            {mounted && time
              ? time.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
              : '-- --- ----'}
          </div>
        </div>
      </div>
    </motion.header>
  );
}
