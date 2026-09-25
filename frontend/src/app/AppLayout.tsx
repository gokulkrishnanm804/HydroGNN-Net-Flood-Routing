'use client';
import React, { useState } from 'react';
import Sidebar from './components/Sidebar';
import TopBar from './components/TopBar';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState<boolean>(false);
  const sidebarWidth = collapsed ? 68 : 240;

  return (
    <div style={{ display: 'flex', minHeight: '100vh', backgroundColor: 'var(--bg-app)' }}>
      {/* Sidebar */}
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((prev) => !prev)} />

      {/* Main Workspace */}
      <div
        style={{
          marginLeft: sidebarWidth,
          flex: 1,
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          transition: 'margin-left 0.2s ease',
          width: `calc(100% - ${sidebarWidth}px)`,
        }}
      >
        {/* TopBar */}
        <div
          style={{
            position: 'sticky',
            top: 0,
            zIndex: 40,
            width: '100%',
          }}
        >
          <TopBar />
        </div>

        {/* Content Container */}
        <main
          style={{
            flex: 1,
            padding: '24px 28px',
            maxWidth: 1600,
            width: '100%',
            boxSizing: 'border-box',
            margin: '0 auto',
          }}
        >
          {children}
        </main>
      </div>
    </div>
  );
}
