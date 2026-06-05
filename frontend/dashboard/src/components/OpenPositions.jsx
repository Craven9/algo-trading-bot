import React, { useState } from 'react'

function RBar({ r }) {
  const clamped = Math.max(-3, Math.min(3, r))
  const pct = Math.abs(clamped) / 3 * 100
  const color = r >= 0 ? 'var(--green)' : 'var(--red)'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ width: 60, height: 4, background: 'var(--bg-elevated)', borderRadius: 2, position: 'relative' }}>
        <div style={{
          position: 'absolute',
          [r >= 0 ? 'left' : 'right']: '50%',
          width: `${pct / 2}%`,
          height: '100%',
          background: color,
          borderRadius: 2,
        }} />
        <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1, background: 'var(--border-bright)' }} />
      </div>
      <span style={{ color, fontSize: 11, fontWeight: 600, minWidth: 32 }}>
        {r >= 0 ? '+' : ''}{r.toFixed(2)}R
      </span>
    </div>
  )
}

export default function OpenPositions({ positions, control }) {
  const [confirmClose, setConfirmClose] = useState(null)

  if (!positions || positions.length === 0) {
    return (
      <div className="card" style={{ flex: 1 }}>
        <div className="card-header">
          <span>Open Positions</span>
          <span className="badge badge-gray">0</span>
        </div>
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
          No open positions
        </div>
      </div>
    )
  }

  const handleClose = async (ticker) => {
    if (confirmClose === ticker) {
      await control.closePosition(ticker)
      setConfirmClose(null)
    } else {
      setConfirmClose(ticker)
      setTimeout(() => setConfirmClose(null), 3000)
    }
  }

  return (
    <div className="card" style={{ flex: 1 }}>
      <div className="card-header">
        <span>Open Positions</span>
        <span className="badge badge-cyan">{positions.length}</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Setup</th>
            <th>Entry</th>
            <th>Current</th>
            <th>P&L</th>
            <th>R</th>
            <th>Stop</th>
            <th>Shares</th>
            <th>Warnings</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {positions.map(p => {
            const pnlColor = p.unrealized_pnl >= 0 ? 'num-positive' : 'num-negative'
            const rowBg = p.exit_warnings?.length > 0 ? 'rgba(255,165,2,0.04)' :
                          p.unrealized_pnl >= 0 ? 'rgba(0,214,143,0.02)' : 'transparent'

            return (
              <tr key={p.ticker} style={{ background: rowBg }} className="fade-in">
                <td>
                  <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 14 }}>{p.ticker}</span>
                  {p.breakeven_set && <span style={{ marginLeft: 6, fontSize: 9, color: 'var(--cyan)', border: '1px solid var(--cyan)', padding: '1px 4px', borderRadius: 2 }}>BE</span>}
                </td>
                <td>
                  <span style={{ fontSize: 10, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    {p.setup_type?.replace(/_/g, ' ')}
                  </span>
                  <br />
                  <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>score {p.setup_score}</span>
                </td>
                <td style={{ fontWeight: 500 }}>${p.entry_price?.toFixed(2)}</td>
                <td style={{ fontWeight: 600 }}>${p.current_price?.toFixed(2)}</td>
                <td>
                  <span className={pnlColor} style={{ fontWeight: 600 }}>
                    {p.unrealized_pnl >= 0 ? '+' : ''}${p.unrealized_pnl?.toFixed(2)}
                  </span>
                  <br />
                  <span className={pnlColor} style={{ fontSize: 10 }}>
                    {p.unrealized_pnl_pct >= 0 ? '+' : ''}{p.unrealized_pnl_pct?.toFixed(2)}%
                  </span>
                </td>
                <td><RBar r={p.r_multiple || 0} /></td>
                <td style={{ color: 'var(--red)', fontWeight: 500 }}>${p.stop_price?.toFixed(2)}</td>
                <td style={{ color: 'var(--text-secondary)' }}>
                  {p.remaining_shares}<span style={{ color: 'var(--text-muted)' }}>/{p.shares}</span>
                </td>
                <td>
                  {p.exit_warnings?.map((w, i) => (
                    <div key={i} style={{ fontSize: 10, color: 'var(--amber)', display: 'flex', alignItems: 'center', gap: 4 }}>
                      <span>⚠</span> {w}
                    </div>
                  ))}
                </td>
                <td>
                  <button
                    className={`btn ${confirmClose === p.ticker ? 'btn-danger' : 'btn-ghost'}`}
                    style={{ fontSize: 10, padding: '4px 10px' }}
                    onClick={() => handleClose(p.ticker)}
                  >
                    {confirmClose === p.ticker ? 'Confirm' : 'Close'}
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
