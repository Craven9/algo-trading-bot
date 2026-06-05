import React from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'

function SetupRow({ name, stats }) {
  if (!stats) return null
  const wr = (stats.win_rate * 100).toFixed(0)
  const wrColor = stats.win_rate >= 0.6 ? 'var(--green)' : stats.win_rate >= 0.5 ? 'var(--amber)' : 'var(--red)'
  const rColor  = stats.avg_r >= 1.0 ? 'var(--green)' : stats.avg_r >= 0 ? 'var(--amber)' : 'var(--red)'

  return (
    <tr>
      <td>
        <span style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-secondary)' }}>
          {name.replace(/_/g, ' ')}
        </span>
      </td>
      <td style={{ color: 'var(--text-muted)', fontSize: 11 }}>{stats.trade_count}</td>
      <td>
        <span style={{ color: wrColor, fontWeight: 600 }}>{wr}%</span>
        <div style={{ marginTop: 2, height: 2, width: 50, background: 'var(--bg-elevated)', borderRadius: 1 }}>
          <div style={{ width: `${stats.win_rate * 100}%`, height: '100%', background: wrColor, borderRadius: 1 }} />
        </div>
      </td>
      <td style={{ color: rColor, fontWeight: 600 }}>
        {stats.avg_r >= 0 ? '+' : ''}{stats.avg_r?.toFixed(2)}R
      </td>
    </tr>
  )
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  const d = payload[0].value
  return (
    <div style={{
      background: 'var(--bg-elevated)', border: '1px solid var(--border)',
      borderRadius: 4, padding: '8px 12px', fontSize: 11,
    }}>
      <div style={{ color: 'var(--text-muted)', marginBottom: 4 }}>{label}</div>
      <div style={{ color: d >= 0 ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>
        {d >= 0 ? '+' : ''}{d?.toFixed(2)}R cumulative
      </div>
    </div>
  )
}

export default function PerformancePanel({ performance }) {
  const stats = performance?.setup_stats || {}
  const curve = performance?.equity_curve || []
  const trades = performance?.today_trades || []

  const totalR = curve[curve.length - 1]?.cumulative_r || 0
  const totalTrades = Object.values(stats).reduce((s, x) => s + (x?.trade_count || 0), 0)
  const overallWR = totalTrades > 0
    ? Object.values(stats).reduce((s, x) => s + (x?.win_rate || 0) * (x?.trade_count || 0), 0) / totalTrades
    : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, flex: 1 }}>
      {/* Summary row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
        {[
          { label: 'Total Trades', value: totalTrades, color: 'var(--text-primary)' },
          { label: 'Overall Win Rate', value: `${(overallWR * 100).toFixed(0)}%`, color: overallWR >= 0.55 ? 'var(--green)' : 'var(--red)' },
          { label: 'Cumulative R', value: `${totalR >= 0 ? '+' : ''}${totalR.toFixed(2)}R`, color: totalR >= 0 ? 'var(--green)' : 'var(--red)' },
        ].map(({ label, value, color }) => (
          <div key={label} className="card" style={{ padding: '14px 16px' }}>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 6 }}>{label}</div>
            <div style={{ fontSize: 22, fontWeight: 700, color, fontFamily: 'var(--font-display)' }}>{value}</div>
          </div>
        ))}
      </div>

      {/* Equity curve */}
      <div className="card">
        <div className="card-header"><span>Equity Curve (R)</span></div>
        <div style={{ padding: '16px 8px 8px' }}>
          <ResponsiveContainer width="100%" height={140}>
            <LineChart data={curve}>
              <XAxis dataKey="date" tick={{ fontSize: 9, fill: 'var(--text-muted)' }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fontSize: 9, fill: 'var(--text-muted)' }} tickLine={false} axisLine={false} width={32} />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine y={0} stroke="var(--border-bright)" strokeDasharray="3 3" />
              <Line
                type="monotone" dataKey="cumulative_r"
                stroke="var(--cyan)" strokeWidth={2} dot={false}
                activeDot={{ r: 4, fill: 'var(--cyan)', strokeWidth: 0 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Setup stats */}
      <div className="card" style={{ flex: 1 }}>
        <div className="card-header"><span>Setup Performance</span></div>
        <table>
          <thead>
            <tr>
              <th>Setup</th>
              <th>Trades</th>
              <th>Win Rate</th>
              <th>Avg R</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(stats).map(([name, s]) => (
              <SetupRow key={name} name={name} stats={s} />
            ))}
          </tbody>
        </table>
      </div>

      {/* Today's closed trades */}
      {trades.length > 0 && (
        <div className="card">
          <div className="card-header"><span>Today's Closed Trades</span></div>
          <table>
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Setup</th>
                <th>R</th>
                <th>P&L</th>
                <th>Exit Reason</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t, i) => (
                <tr key={i}>
                  <td style={{ fontFamily: 'var(--font-display)', fontWeight: 700 }}>{t.ticker}</td>
                  <td style={{ fontSize: 10, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>{t.setup_type?.replace(/_/g, ' ')}</td>
                  <td style={{ color: t.r_multiple >= 0 ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>
                    {t.r_multiple >= 0 ? '+' : ''}{t.r_multiple?.toFixed(2)}R
                  </td>
                  <td style={{ color: t.realized_pnl >= 0 ? 'var(--green)' : 'var(--red)' }}>
                    {t.realized_pnl >= 0 ? '+' : ''}${t.realized_pnl?.toFixed(0)}
                  </td>
                  <td style={{ fontSize: 11, color: 'var(--text-muted)' }}>{t.exit_reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
