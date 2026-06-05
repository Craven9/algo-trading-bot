import React, { useState } from 'react'

export default function RejectionsPanel({ rejections }) {
  const [expanded, setExpanded] = useState(null)

  if (!rejections || rejections.length === 0) {
    return (
      <div className="card" style={{ flex: 1 }}>
        <div className="card-header"><span>Rejection Log</span><span className="badge badge-gray">0</span></div>
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
          No rejections today
        </div>
      </div>
    )
  }

  const sorted = [...rejections].reverse()

  return (
    <div className="card" style={{ flex: 1 }}>
      <div className="card-header">
        <span>Rejection Log</span>
        <span className="badge badge-gray">{rejections.length}</span>
      </div>
      <div style={{ maxHeight: 400, overflowY: 'auto' }}>
        {sorted.map((r, i) => (
          <div
            key={i}
            style={{
              borderBottom: '1px solid var(--border)',
              cursor: 'pointer',
              background: expanded === i ? 'var(--bg-elevated)' : 'transparent',
              transition: 'background 0.15s',
            }}
            onClick={() => setExpanded(expanded === i ? null : i)}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px' }}>
              <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 14, minWidth: 56 }}>
                {r.ticker}
              </span>
              <span style={{ flex: 1, fontSize: 11, color: 'var(--red)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {r.reasons?.[0]}
              </span>
              {r.reasons?.length > 1 && (
                <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>+{r.reasons.length - 1} more</span>
              )}
              <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                {r.timestamp ? new Date(r.timestamp).toLocaleTimeString() : ''}
              </span>
              <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{expanded === i ? '▲' : '▼'}</span>
            </div>
            {expanded === i && (
              <div style={{ padding: '0 14px 12px', borderTop: '1px solid var(--border)' }}>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 8, marginTop: 8, textTransform: 'uppercase', letterSpacing: '0.08em' }}>All Rejection Reasons</div>
                {r.reasons?.map((reason, j) => (
                  <div key={j} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 4 }}>
                    <span style={{ color: 'var(--red)', fontSize: 12, marginTop: 1 }}>✗</span>
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{reason}</span>
                  </div>
                ))}
                {r.score_breakdown?.score !== undefined && (
                  <div style={{ marginTop: 10, padding: '8px 10px', background: 'var(--bg-surface)', borderRadius: 4, fontSize: 11, color: 'var(--text-muted)' }}>
                    Setup score: <span style={{ color: 'var(--amber)' }}>{r.score_breakdown.score}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
