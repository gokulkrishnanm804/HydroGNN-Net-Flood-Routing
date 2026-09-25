'use client';
import React from 'react';
import AppLayout from '../AppLayout';
import {
  Brain,
  Layers,
  Zap,
  Activity,
  GitBranch,
  ShieldCheck,
  CheckCircle,
  Network,
  Cpu,
  ArrowRight,
} from 'lucide-react';

const ARCHITECTURE_STEPS = [
  { step: '01', title: 'Historical Input', desc: '24-hour sequence (7 features per river station: stage, rainfall, discharge, storage, moisture, temp, humidity)', icon: Activity },
  { step: '02', title: 'Recurrent GRU', desc: '2-layer GRU (hidden=64) extracts local temporal trends and hydrograph slope dynamics', icon: Zap },
  { step: '03', title: 'GATv2 Attention', desc: '2 layers with 4 dynamic attention heads model multi-scale reach spatial interactions', icon: GitBranch },
  { step: '04', title: 'GraphSAGE Layer', desc: 'Inductive neighbor aggregation (hidden=64) over topological river network edges', icon: Network },
  { step: '05', title: 'Multi-Horizon Head', desc: 'Dedicated linear heads predict native 6h, 12h, and 24h future stage levels', icon: Layers },
  { step: '06', title: 'Uncertainty Interval', desc: 'Heteroscedastic confidence modeling outputs 95% predictive bounds for decision support', icon: ShieldCheck },
];

const MODEL_CONFIG_ITEMS = [
  { label: 'Model Identifier', value: 'HydroGNN-Net (Exp 9)' },
  { label: 'Trainable Parameters', value: '72,594' },
  { label: 'Node Features', value: '7' },
  { label: 'Edge Features', value: '3' },
  { label: 'Hidden Dimension', value: '64' },
  { label: 'GRU Layers', value: '2' },
  { label: 'GATv2 Layers', value: '2' },
  { label: 'GAT Heads', value: '4' },
  { label: 'GraphSAGE Hidden', value: '64' },
  { label: 'Dropout Rate', value: '0.2' },
  { label: 'Historical Window', value: '24 Hours' },
  { label: 'Native Forecast Horizons', value: '6h, 12h, 24h' },
];

export default function ModelPage() {
  return (
    <AppLayout>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        {/* Header */}
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
            HydroGNN-Net Spatio-Temporal Model
          </h2>
          <p style={{ fontSize: '0.82rem', color: '#94a3b8', margin: '3px 0 0' }}>
            Verified Graph Neural Network architecture and held-out test evaluation benchmarks
          </p>
        </div>

        {/* 1. HELD-OUT TEST EVALUATION (Prominently Highlighted) */}
        <div
          className="card"
          style={{
            padding: '20px 24px',
            border: '1px solid rgba(14, 165, 233, 0.35)',
            backgroundColor: 'rgba(14, 165, 233, 0.04)',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 16,
              flexWrap: 'wrap',
              gap: 8,
            }}
          >
            <div>
              <div
                style={{
                  fontSize: '0.72rem',
                  color: '#38bdf8',
                  textTransform: 'uppercase',
                  fontWeight: 700,
                  letterSpacing: '0.06em',
                }}
              >
                Verification Benchmark
              </div>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#f8fafc', margin: '2px 0 0' }}>
                Held-out Test Evaluation
              </h3>
            </div>

            <span
              style={{
                backgroundColor: 'rgba(16, 185, 129, 0.12)',
                border: '1px solid rgba(16, 185, 129, 0.28)',
                color: '#10b981',
                padding: '3px 10px',
                borderRadius: 4,
                fontSize: '0.74rem',
                fontWeight: 600,
              }}
            >
              Experiment 9 · Checkpoint: Models/best_model.pt
            </span>
          </div>

          <p style={{ fontSize: '0.8rem', color: '#94a3b8', maxWidth: 720, margin: '0 0 18px' }}>
            Strict offline held-out test evaluation across the 8-station Cauvery River Basin network. Nash-Sutcliffe Efficiency (NSE) reflects hydrodynamic skill relative to variance, bounded at 1.0.
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
            <div
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 6,
                padding: '14px 18px',
              }}
            >
              <div style={{ fontSize: '0.72rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>
                Test NSE (Nash-Sutcliffe Efficiency)
              </div>
              <div
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '2.1rem',
                  fontWeight: 800,
                  color: '#38bdf8',
                  lineHeight: 1.2,
                  margin: '4px 0',
                }}
              >
                0.9968
              </div>
              <div style={{ fontSize: '0.7rem', color: '#64748b' }}>
                Held-out Test Evaluation
              </div>
            </div>

            <div
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 6,
                padding: '14px 18px',
              }}
            >
              <div style={{ fontSize: '0.72rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>
                Test RMSE (Root Mean Square Error)
              </div>
              <div
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '2.1rem',
                  fontWeight: 800,
                  color: '#10b981',
                  lineHeight: 1.2,
                  margin: '4px 0',
                }}
              >
                0.4974 <span style={{ fontSize: '1rem', fontWeight: 400, color: '#64748b' }}>m</span>
              </div>
              <div style={{ fontSize: '0.7rem', color: '#64748b' }}>
                Stage error across all test time steps
              </div>
            </div>

            <div
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 6,
                padding: '14px 18px',
              }}
            >
              <div style={{ fontSize: '0.72rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>
                Test MAE (Mean Absolute Error)
              </div>
              <div
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '2.1rem',
                  fontWeight: 800,
                  color: '#f8fafc',
                  lineHeight: 1.2,
                  margin: '4px 0',
                }}
              >
                0.1786 <span style={{ fontSize: '1rem', fontWeight: 400, color: '#64748b' }}>m</span>
              </div>
              <div style={{ fontSize: '0.7rem', color: '#64748b' }}>
                Average absolute error across river reaches
              </div>
            </div>
          </div>
        </div>

        {/* 2. ARCHITECTURE PIPELINE FLOW DIAGRAM */}
        <div className="card" style={{ padding: '20px 22px' }}>
          <div className="card-title" style={{ marginBottom: 16 }}>
            <Layers size={16} color="#0ea5e9" />
            <span>End-to-End Deep Learning Architecture Flow</span>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: 12,
            }}
          >
            {ARCHITECTURE_STEPS.map((step, idx) => {
              const Icon = step.icon;
              return (
                <div
                  key={step.step}
                  style={{
                    backgroundColor: 'var(--bg-surface)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 6,
                    padding: '14px 16px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 6,
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: '#0ea5e9', fontWeight: 700 }}>
                      STAGE {step.step}
                    </span>
                    <Icon size={14} color="#94a3b8" />
                  </div>
                  <h4 style={{ fontSize: '0.88rem', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
                    {step.title}
                  </h4>
                  <p style={{ fontSize: '0.72rem', color: '#94a3b8', lineHeight: 1.4, margin: 0 }}>
                    {step.desc}
                  </p>
                </div>
              );
            })}
          </div>
        </div>

        {/* 3. MODEL CONFIGURATION PARAMETERS TABLE */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <Cpu size={15} color="#0ea5e9" />
              <span>Experiment 9 Verified Hyperparameters & Specifications</span>
            </div>
            <span style={{ fontSize: '0.72rem', color: '#64748b' }}>
              PyTorch State Dict Specs
            </span>
          </div>

          <div className="card-body" style={{ padding: '16px 20px' }}>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
                gap: 12,
              }}
            >
              {MODEL_CONFIG_ITEMS.map((item) => (
                <div
                  key={item.label}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '8px 12px',
                    backgroundColor: 'var(--bg-surface)',
                    borderRadius: 4,
                    border: '1px solid var(--border-subtle)',
                    fontSize: '0.78rem',
                  }}
                >
                  <span style={{ color: '#94a3b8' }}>{item.label}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: '#f8fafc' }}>
                    {item.value}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
