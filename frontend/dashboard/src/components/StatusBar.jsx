import React from 'react'

function fmt(val) {
  if (val === undefined || val === null) return '—'
  return val
}

function pnlColor(val) {
  if (!val && val !== 0) return ''
  return val >= 0 ? 'num-positive' : 'num-negative'
}

export default function StatusBar({ status, account, lastUpdate, control }) {
  const acc = account || {}
  const mode = status?.mode || {}
  const session = status?.session || '—'

  const modeLabel = mode.dry_run ? 'DRY RUN' : mode.paper_trading ? 'PAPER' : 'LIVE'
  const modeBadge = mode.dry_run ? 'badge-amber' : mode.paper_trading ? 'badge-cyan' : 'badge-red'

  const sessionColor = {
    ACTIVE: 'text-green', OPENING: 'text-amber', PRE_MARKET: 'text-secondary',
    EOD: 'text-amber', AFTER_HOURS: 'text-muted', CLOSED: 'text-muted',
  }[session] || 'text-secondary'

  const lossUsed = acc.daily_loss_limit_used_pct || 0
  const lossBarColor = lossUsed > 80 ? '#ff4757' : lossUsed > 50 ? '#ffa502' : '#00d68f'

  return (
    <header style={{
      display: 'flex', alignItems: 'center', gap: 0,
      background: 'var(--bg-surface)',
      borderBottom: '1px solid var(--border)',
      padding: '0 20px',
      height: 52,
      flexShrink: 0,
    }}>
      {/* Logo */}
      <div style={{ marginRight: 28, display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{
          width: 28, height: 28, borderRadius: 4,
          background: 'linear-gradient(135deg, var(--cyan), var(--green))',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 13, fontWeight: 800, color: 'var(--bg-base)',
          fontFamily: 'var(--font-display)',
        }}>A</div>
        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 14, letterSpacing: '0.05em' }}>
          ALGO<span style={{ color: 'var(--cyan)' }}>BOT</span>
        </span>
      </div>

      {/* Mode */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginRight: 24 }}>
        <span className={`badge ${modeBadge}`}>{modeLabel}</span>
        {status?.running && !status?.paused && <span className="live-dot" />}
        {status?.paused && <span className="badge badge-amber">PAUSED</span>}
      </div>

      {/* Divider */}
      <div style={{ width: 1, height: 28, background: 'var(--border)', marginRight: 24 }} />

      {/* Session */}
      <div style={{ marginRight: 28 }}>
        <span style={{ fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>SESSION </span>
        <span className={`${sessionColor}`} style={{ fontWeight: 600 }}>{session}</span>
      </div>

      {/* Daily P&L */}
      <div style={{ marginRight: 28 }}>
        <span style={{ fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>DAY P&L </span>
        <span className={pnlColor(acc.daily_total_pnl)} style={{ fontWeight: 600 }}>
          {acc.daily_total_pnl >= 0 ? '+' : ''}${(acc.daily_total_pnl || 0).toFixed(2)}
        </span>
      </div>

      {/* Loss limit bar */}
      <div style={{ marginRight: 28, display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>RISK USED</span>
        <div style={{ width: 80, height: 4, background: 'var(--bg-elevated)', borderRadius: 2, overflow: 'hidden' }}>
          <div style={{ width: `${Math.min(lossUsed, 100)}%`, height: '100%', background: lossBarColor, transition: 'width 0.5s ease' }} />
        </div>
        <span style={{ fontSize: 11, color: lossBarColor }}>{lossUsed.toFixed(0)}%</span>
      </div>

      {/* Positions */}
      <div style={{ marginRight: 28 }}>
        <span style={{ fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>POSITIONS </span>
        <span style={{ fontWeight: 600 }}>{acc.open_positions || 0}<span style={{ color: 'var(--text-muted)' }}>/{acc.max_positions || 4}</span></span>
      </div>

      {/* Equity */}
      <div style={{ marginRight: 'auto' }}>
        <span style={{ fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>EQUITY </span>
        <span style={{ fontWeight: 600 }}>${(acc.equity || 0).toLocaleString()}</span>
      </div>

      {/* Last update */}
      <span style={{ fontSize: 10, color: 'var(--text-muted)', marginRight: 20 }}>
        {lastUpdate ? lastUpdate.toLocaleTimeString() : '—'}
      </span>

      {/* Controls */}
      <div style={{ display: 'flex', gap: 8 }}>
        {status?.paused
          ? <button className="btn btn-ghost" onClick={control.resume}>Resume</button>
          : <button className="btn btn-ghost" onClick={control.pause}>Pause</button>
        }
        <button className="btn btn-danger" onClick={() => { if(confirm('Close ALL positions?')) control.emergencyClose() }}>
          ⚡ Emergency Close
        </button>
      </div>
    </header>
  )
}
