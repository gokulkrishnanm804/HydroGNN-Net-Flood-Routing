'use client';
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Sidebar from './components/Sidebar';
import TopBar from './components/TopBar';
import NeuralBackground from './components/NeuralBackground';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const sidebarW = collapsed ? 72 : 264;

  return (
    <div style={{ display: 'flex', minHeight: '100vh', position: 'relative' }}>
      {/* Layered backgrounds */}
      <NeuralBackground />
      <div className="bg-mesh" />
      <div className="bg-aurora" />

      {/* Sidebar */}
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} />

      {/* Main */}
      <motion.main
        style={{ flex: 1, minHeight: '100vh', position: 'relative', zIndex: 1, display: 'flex', flexDirection: 'column' }}
        animate={{ marginLeft: sidebarW }}
        transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
      >
        {/* TopBar adapts to sidebar width */}
        <motion.div
          style={{ position: 'fixed', top: 0, right: 0, zIndex: 90 }}
          animate={{ left: sidebarW }}
          transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
        >
          <TopBar />
        </motion.div>

        {/* Page content area below fixed TopBar */}
        <div style={{ paddingTop: 64, flex: 1, display: 'flex', flexDirection: 'column' }}>
          <AnimatePresence mode="wait">
            <motion.div
              key={typeof window !== 'undefined' ? window.location.pathname : 'p'}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
              style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
            >
              {children}
            </motion.div>
          </AnimatePresence>
        </div>
      </motion.main>
    </div>
  );
}
