import React, { useState } from 'react'
import StatusBar from './components/StatusBar.jsx'
import OpenPositions from './components/OpenPositions.jsx'
import PerformancePanel from './components/PerformancePanel.jsx'
import RejectionsPanel from './components/RejectionsPanel.jsx'
import { useApi, useMockData } from './hooks/useApi.js'

// Detect if backend is available; use mock data if not
const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

function AccountCard({ account }) {
  const acc = account || {}
  const items = [
    { label: 'Equity', value: `$${(acc.equity || 0).toLocaleString()}` },
    { label: 'Day P&L', value: `${(acc.daily_total_pnl || 0) >= 0 ? '+' : ''}$${(acc.daily_total_pnl || 0).toFixed(2)}`, color: (acc.daily_total_pnl || 0) >= 0 ? 'var(--green)' : 'var(--red)' },
    { label: 'Realized', value: `$${(acc.daily_realized_pnl || 0).toFixed(2)}`, color: (acc.daily_realized_pnl || 0) >= 0 ? 'var(--green)' : 'var(--red)' },
    { label: 'Exposure', value: `${(acc.exposure_pct || 0).toFixed(1)}%`, color: (acc.exposure_pct || 0) > 25 ? 'var(--amber)' : 'var(--text-primary)' },
    { label: 'Streak', value: acc.consecutive_losses > 0 ? `${acc.consecutive_losses}L` : '—', color: acc.consecutive_losses > 1 ? 'var(--red)' : 'var(--text-secondary)' },
    { label: 'Trades Today', value: acc.trades_today || 0 },
  ]

  return (
    <div className="card">
      <div className="card-header"><span>Account</span></div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 0 }}>
        {items.map(({ label, value, color }) => (
          <div key={label} style={{ padding: '12px 14px', borderBottom: '1px solid var(--border)', borderRight: '1px solid var(--border)' }}>
            <div style={{ fontSize: 9, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 4 }}>{label}</div>
            <div style={{ fontWeight: 600, fontSize: 14, color: color || 'var(--text-primary)' }}>{value}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function TabBar({ active, onChange }) {
  const tabs = [
    { id: 'positions', label: 'Positions' },
    { id: 'performance', label: 'Performance' },
    { id: 'rejections', label: 'Rejections' },
  ]
  return (
    <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid var(--border)', marginBottom: 16 }}>
      {tabs.map(t => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          style={{
            padding: '10px 20px',
            background: 'transparent',
            color: active === t.id ? 'var(--cyan)' : 'var(--text-muted)',
            borderBottom: active === t.id ? '2px solid var(--cyan)' : '2px solid transparent',
            marginBottom: -1,
            fontSize: 11,
            fontFamily: 'var(--font-display)',
            fontWeight: 700,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            transition: 'all 0.15s',
            borderRadius: 0,
          }}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

export default function App() {
  const liveData = useApi(5000)
  const mockData = useMockData()
  const data = USE_MOCK ? mockData : liveData
  const [activeTab, setActiveTab] = useState('positions')

  const { status, positions, account, performance, rejections, loading, lastUpdate, control } = data

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      {/* Top bar */}
      <StatusBar status={status} account={account} lastUpdate={lastUpdate} control={control} />

      {/* Scanline effect */}
      <div style={{
        position: 'fixed', top: 0, left: 0, right: 0, height: '2px',
        background: 'linear-gradient(90deg, transparent, var(--cyan), transparent)',
        opacity: 0.3, zIndex: 10,
        animation: 'scanline 8s linear infinite',
        pointerEvents: 'none',
      }} />

      {/* Main content */}
      <div style={{ flex: 1, overflow: 'auto', padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Account row */}
        <AccountCard account={account} />

        {/* Tabs */}
        <TabBar active={activeTab} onChange={setActiveTab} />

        {/* Tab content */}
        {activeTab === 'positions' && (
          <OpenPositions positions={positions} control={control} />
        )}
        {activeTab === 'performance' && (
          <PerformancePanel performance={performance} />
        )}
        {activeTab === 'rejections' && (
          <RejectionsPanel rejections={rejections} />
        )}
      </div>

      {/* Loading overlay */}
      {loading && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(8,12,14,0.9)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 100, flexDirection: 'column', gap: 16,
        }}>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 700 }}>
            ALGO<span style={{ color: 'var(--cyan)' }}>BOT</span>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            {[0, 1, 2].map(i => (
              <div key={i} style={{
                width: 6, height: 6, borderRadius: '50%', background: 'var(--cyan)',
                animation: `pulse 1s ease-in-out ${i * 0.2}s infinite`,
              }} />
            ))}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Connecting to bot...</div>
        </div>
      )}
    </div>
  )
}
