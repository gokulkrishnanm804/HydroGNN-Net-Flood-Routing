'use client';

import React from 'react';
import { motion } from 'framer-motion';
import AppLayout from '../AppLayout';
import PageHeader from '../components/PageHeader';
import {
  BookOpen,
  Radio,
  Cpu,
  Activity,
  Layers,
  Award,
  ShieldAlert,
  CheckCircle2,
  AlertTriangle,
  Flame,
  Info,
  ArrowRight
} from 'lucide-react';

interface GuideSectionProps {
  number: string;
  title: string;
  badge?: string;
  badgeColor?: string;
  icon: React.ComponentType<{ size?: number; color?: string }>;
  iconColor: string;
  children: React.ReactNode;
}

function GuideCard({ number, title, badge, badgeColor = '#38bdf8', icon: Icon, iconColor, children }: GuideSectionProps) {
  return (
    <motion.div
      className="glass-card"
      style={{
        padding: '24px 28px',
        borderTop: `2px solid ${iconColor}`,
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
      }}
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 8,
              background: `${iconColor}15`,
              border: `1px solid ${iconColor}30`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <Icon size={18} color={iconColor} />
          </div>
          <div>
            <div style={{ fontSize: '0.68rem', color: 'rgba(255,255,255,0.45)', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 700 }}>
              Section {number}
            </div>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 800, color: '#f8fafc', margin: 0 }}>
              {title}
            </h3>
          </div>
        </div>
        {badge && (
          <span
            style={{
              padding: '4px 10px',
              borderRadius: 6,
              fontSize: '0.72rem',
              fontWeight: 700,
              background: `${badgeColor}15`,
              border: `1px solid ${badgeColor}40`,
              color: badgeColor,
            }}
          >
            {badge}
          </span>
        )}
      </div>

      <div style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.72)', lineHeight: 1.65 }}>
        {children}
      </div>
    </motion.div>
  );
}

export default function HelpPage() {
  return (
    <AppLayout>
      <div style={{ padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 24, maxWidth: 1400, margin: '0 auto', width: '100%' }}>

        {/* Standardized Government Page Header */}
        <PageHeader
          title="HydroGNN-Net User Guide"
          subtitle="How to interpret the flood-monitoring dashboard"
          purpose="Comprehensive reference guide explaining system purpose, data classifications, forecasting models, and operational flood thresholds for government evaluators and operators."
          badges={[
            { label: 'System Guide & Reference', variant: 'info' },
            { label: 'Verified Model: Experiment 9', variant: 'safe' },
            { label: 'River Basin: Cauvery', variant: 'info' },
          ]}
        />

        {/* Quick Orientation Banner */}
        <motion.div
          className="glass-card gradient-border"
          style={{ padding: '20px 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 20, flexWrap: 'wrap' }}
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <BookOpen size={24} color="#38bdf8" />
            <div>
              <div style={{ fontSize: '0.9rem', fontWeight: 800, color: '#f8fafc' }}>
                Executive Orientation & Decision Support Rules
              </div>
              <div style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.55)', marginTop: 2 }}>
                Every data element in this dashboard maintains strict provenance between Live Telemetry, Hydrological Models, and Experiment 9 Neural Predictions.
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <a href="/" className="btn btn-primary" style={{ fontSize: '0.78rem', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              Open Dashboard <ArrowRight size={13} />
            </a>
          </div>
        </motion.div>

        {/* 7 Core Guide Sections */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: 18 }}>

          {/* 1. WHAT IS HYDROGNN-NET? */}
          <GuideCard
            number="01"
            title="What is HydroGNN-Net?"
            badge="Decision Support"
            badgeColor="#38bdf8"
            icon={Activity}
            iconColor="#38bdf8"
          >
            <p style={{ margin: 0, marginBottom: 10 }}>
              <strong>HydroGNN-Net</strong> is an operational decision-support system designed for real-time river-level monitoring and flood forecasting across the Cauvery River Basin.
            </p>
            <p style={{ margin: 0, color: 'rgba(255,255,255,0.6)' }}>
              It integrates live hydrological telemetry, multi-source weather radar observations, physical reservoir routing dynamics, and spatio-temporal graph neural networks to help dam operators, emergency managers, and government flood-control agencies plan proactive flood defenses.
            </p>
          </GuideCard>

          {/* 2. WHAT IS LIVE? */}
          <GuideCard
            number="02"
            title="What is Live?"
            badge="Telemetry Stream"
            badgeColor="#34d399"
            icon={Radio}
            iconColor="#34d399"
          >
            <p style={{ margin: 0, marginBottom: 10 }}>
              <strong>Live Data</strong> represents observed and ingested sensor measurements arriving directly from operational telemetry feeds:
            </p>
            <ul style={{ margin: 0, paddingLeft: 20, display: 'flex', flexDirection: 'column', gap: 6, color: 'rgba(255,255,255,0.65)' }}>
              <li><strong>River Gauges:</strong> Ground station stage heights (measured in feet) at critical monitoring points like Mettur, Erode, Urachikottai, and Musiri.</li>
              <li><strong>Weather Feeds:</strong> Near-real-time precipitation and atmospheric conditions ingested from meteorological APIs.</li>
              <li><strong>Reservoir Inflow/Outflow:</strong> Monitored dam releases and live storage percentages.</li>
            </ul>
          </GuideCard>

          {/* 3. WHAT IS EXPERIMENT 9? */}
          <GuideCard
            number="03"
            title="What is Experiment 9?"
            badge="Spatio-Temporal GNN"
            badgeColor="#a78bfa"
            icon={Cpu}
            iconColor="#a78bfa"
          >
            <p style={{ margin: 0, marginBottom: 10 }}>
              <strong>Experiment 9</strong> is the trained spatio-temporal Graph Neural Network utilized for native <strong>6h, 12h, and 24h</strong> river stage level forecasts.
            </p>
            <p style={{ margin: 0, marginBottom: 8, color: 'rgba(255,255,255,0.6)' }}>
              <strong>Architecture Pipeline:</strong> Temporal GRU (capturing historical lag dynamics) → GATv2 Attention + GraphSAGE (capturing upstream/downstream river graph topology) → Stage Projection → Trend-Conditioned Residual Gating.
            </p>
            <p style={{ margin: 0, color: '#38bdf8', fontSize: '0.78rem', fontWeight: 600 }}>
              Verified Held-Out Test Evaluation: Test NSE = 0.9968 | Test RMSE = 0.4974 m | Test MAE = 0.1786 m.
            </p>
          </GuideCard>

          {/* 4. WHAT IS PCHIP? */}
          <GuideCard
            number="04"
            title="What is PCHIP?"
            badge="Spline Interpolation"
            badgeColor="#fb923c"
            icon={Layers}
            iconColor="#fb923c"
          >
            <p style={{ margin: 0, marginBottom: 10 }}>
              <strong>PCHIP (Piecewise Cubic Hermite Interpolating Polynomial)</strong> is a shape-preserving mathematical spline method.
            </p>
            <p style={{ margin: 0, color: 'rgba(255,255,255,0.6)' }}>
              While the neural network natively evaluates anchors at <strong>6h, 12h, and 24h</strong>, operational dam managers often require continuous hydrograph trends. PCHIP smoothly interpolates intermediate forecast views at <strong>1h, 3h, and 18h</strong> between the live observed stage and model anchors without introducing non-physical overshoot or artificial oscillations.
            </p>
          </GuideCard>

          {/* 5. WHAT IS THE HYDROLOGICAL MODEL? */}
          <GuideCard
            number="05"
            title="What is the Hydrological Model?"
            badge="Physical Routing"
            badgeColor="#06b6d4"
            icon={Activity}
            iconColor="#06b6d4"
          >
            <p style={{ margin: 0, marginBottom: 10 }}>
              The <strong>Hydrological Model</strong> is the mass-balance and reservoir routing component responsible for physical water calculations:
            </p>
            <ul style={{ margin: 0, paddingLeft: 20, display: 'flex', flexDirection: 'column', gap: 6, color: 'rgba(255,255,255,0.65)' }}>
              <li><strong>Reservoir Operations:</strong> Storage volumes, spillway capacity limits, and rule-based reservoir release estimates.</li>
              <li><strong>Kinematic Wave Routing:</strong> Reach-to-reach propagation velocity and discharge transmission along river segments.</li>
            </ul>
            <div style={{ marginTop: 10, fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>
              Note: Reservoir operations and reach flood routing are governed by physical hydrological principles, distinct from the Exp 9 neural network gauge predictions.
            </div>
          </GuideCard>

          {/* 6. WHAT DOES NSE MEAN? */}
          <GuideCard
            number="06"
            title="What does NSE mean?"
            badge="Hydrological Metric"
            badgeColor="#22d3ee"
            icon={Award}
            iconColor="#22d3ee"
          >
            <p style={{ margin: 0, marginBottom: 10 }}>
              <strong>NSE (Nash-Sutcliffe Efficiency)</strong> is the global benchmark metric used in hydrologic engineering to evaluate the predictive power of hydrological models.
            </p>
            <div style={{ background: 'rgba(0,0,0,0.3)', padding: '10px 14px', borderRadius: 8, fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: '#38bdf8', marginBottom: 10 }}>
              NSE = 1 - [ Σ (Q_obs - Q_sim)² / Σ (Q_obs - Q_mean)² ]
            </div>
            <p style={{ margin: 0, color: 'rgba(255,255,255,0.6)' }}>
              An NSE of <strong>1.0</strong> indicates a perfect match of modeled discharge to observed data. An NSE &gt; 0.75 is categorized as "very good" by hydrological standards. <em>NSE is not classification accuracy</em>; it measures relative variance explained across the river hydrograph.
            </p>
          </GuideCard>
        </div>

        {/* 7. WHAT DO THE COLORS / STATUS LABELS MEAN? */}
        <motion.div
          className="glass-card"
          style={{
            padding: '28px 32px',
            borderTop: '2px solid #fb7185',
            display: 'flex',
            flexDirection: 'column',
            gap: 20,
          }}
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.1 }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: 8,
                background: 'rgba(251,113,133,0.15)',
                border: '1px solid rgba(251,113,133,0.3)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <ShieldAlert size={18} color="#fb7185" />
            </div>
            <div>
              <div style={{ fontSize: '0.68rem', color: 'rgba(255,255,255,0.45)', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 700 }}>
                Section 07
              </div>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 800, color: '#f8fafc', margin: 0 }}>
                What do the Colors and Operational Status Labels mean?
              </h3>
            </div>
          </div>

          <p style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.7)', margin: 0 }}>
            Every river gauging station and reservoir in HydroGNN-Net is dynamically classified based on verified physical thresholds established by the Central Water Commission (CWC) and State Water Resources Department:
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 14 }}>

            {/* Safe */}
            <div style={{ background: 'rgba(52,211,153,0.06)', border: '1px solid rgba(52,211,153,0.25)', borderRadius: 10, padding: '16px 18px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <CheckCircle2 size={16} color="#34d399" />
                <span style={{ fontWeight: 800, color: '#34d399', fontSize: '0.85rem' }}>SAFE (Normal Stage)</span>
              </div>
              <div style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.65)', lineHeight: 1.5 }}>
                Water level is well within normal bankfull capacity (&lt; 75% of danger threshold). Standard continuous monitoring protocol active.
              </div>
            </div>

            {/* Alert */}
            <div style={{ background: 'rgba(56,189,248,0.06)', border: '1px solid rgba(56,189,248,0.25)', borderRadius: 10, padding: '16px 18px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <Info size={16} color="#38bdf8" />
                <span style={{ fontWeight: 800, color: '#38bdf8', fontSize: '0.85rem' }}>ALERT (Rising Water)</span>
              </div>
              <div style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.65)', lineHeight: 1.5 }}>
                Water level has reached 75% to 85% of danger threshold or rising rapidly. Upstream radar and rainfall feeds flagged for heightened scrutiny.
              </div>
            </div>

            {/* Warning */}
            <div style={{ background: 'rgba(251,191,36,0.06)', border: '1px solid rgba(251,191,36,0.25)', borderRadius: 10, padding: '16px 18px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <AlertTriangle size={16} color="#fbbf24" />
                <span style={{ fontWeight: 800, color: '#fbbf24', fontSize: '0.85rem' }}>WARNING (Pre-Flood)</span>
              </div>
              <div style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.65)', lineHeight: 1.5 }}>
                Water level is between 85% and 95% of danger threshold. Operational rule-based advisories recommend preparing spillways and notifying local authorities.
              </div>
            </div>

            {/* Danger */}
            <div style={{ background: 'rgba(251,113,133,0.08)', border: '1px solid rgba(251,113,133,0.3)', borderRadius: 10, padding: '16px 18px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <Flame size={16} color="#fb7185" />
                <span style={{ fontWeight: 800, color: '#fb7185', fontSize: '0.85rem' }}>DANGER (Flood Stage)</span>
              </div>
              <div style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.65)', lineHeight: 1.5 }}>
                Water level is at or above the designated Danger Level (&gt; 95%). High-risk flood advisory triggered; downstream emergency evacuation alerts activated.
              </div>
            </div>
          </div>
        </motion.div>

      </div>
    </AppLayout>
  );
}
