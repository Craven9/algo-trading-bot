import { useState, useEffect, useCallback } from 'react'

const BASE = '/api'

async function apiFetch(path) {
  try {
    const res = await fetch(BASE + path)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
  } catch (e) {
    console.warn(`API error ${path}:`, e.message)
    return null
  }
}

async function apiPost(path) {
  try {
    const res = await fetch(BASE + path, { method: 'POST' })
    return await res.json()
  } catch (e) {
    console.warn(`API post error ${path}:`, e.message)
    return null
  }
}

export function useApi(refreshMs = 5000) {
  const [status, setStatus]       = useState(null)
  const [positions, setPositions] = useState([])
  const [account, setAccount]     = useState(null)
  const [performance, setPerformance] = useState(null)
  const [rejections, setRejections]   = useState([])
  const [loading, setLoading]     = useState(true)
  const [lastUpdate, setLastUpdate] = useState(null)

  const refresh = useCallback(async () => {
    const [s, p, a, perf, r] = await Promise.all([
      apiFetch('/status'),
      apiFetch('/positions'),
      apiFetch('/account'),
      apiFetch('/performance'),
      apiFetch('/rejections'),
    ])
    if (s) setStatus(s)
    if (p) setPositions(p)
    if (a) setAccount(a)
    if (perf) setPerformance(perf)
    if (r) setRejections(r)
    setLastUpdate(new Date())
    setLoading(false)
  }, [])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, refreshMs)
    return () => clearInterval(interval)
  }, [refresh, refreshMs])

  const control = {
    pause:          () => apiPost('/control/pause'),
    resume:         () => apiPost('/control/resume'),
    stop:           () => apiPost('/control/stop'),
    emergencyClose: () => apiPost('/control/emergency-close'),
    closePosition:  (ticker) => apiPost(`/control/close/${ticker}`),
  }

  return { status, positions, account, performance, rejections, loading, lastUpdate, refresh, control }
}

// Mock data for development when backend is offline
export function useMockData() {
  return {
    loading: false,
    lastUpdate: new Date(),
    status: {
      running: true,
      paused: false,
      mode: { dry_run: true, paper_trading: true },
      session: 'ACTIVE',
      open_positions: 2,
      daily_pnl: 842.50,
      account: {
        equity: 100000,
        daily_realized_pnl: 420.00,
        daily_loss_pct: 0.4,
        daily_loss_limit: 3.0,
        daily_loss_limit_used_pct: 13.3,
        open_positions: 2,
        max_positions: 4,
        exposure_pct: 14.2,
        max_exposure_pct: 30,
        consecutive_losses: 0,
        trades_today: 3,
      }
    },
    positions: [
      {
        ticker: 'NVDA', entry_price: 124.50, current_price: 128.20, shares: 80,
        remaining_shares: 48, stop_price: 122.00, unrealized_pnl: 273.60,
        unrealized_pnl_pct: 3.05, r_multiple: 1.42, setup_type: 'vwap_reclaim',
        setup_score: 78, entry_time: new Date(Date.now() - 45*60000).toISOString(),
        breakeven_set: true, first_partial_taken: true, targets: [130.5, 133.0, 137.5],
        exit_warnings: [],
      },
      {
        ticker: 'SMCI', entry_price: 42.10, current_price: 41.80, shares: 200,
        remaining_shares: 200, stop_price: 40.50, unrealized_pnl: -60.00,
        unrealized_pnl_pct: -0.71, r_multiple: -0.19, setup_type: 'break_and_hold',
        setup_score: 71, entry_time: new Date(Date.now() - 18*60000).toISOString(),
        breakeven_set: false, first_partial_taken: false, targets: [44.5, 46.0, 48.0],
        exit_warnings: ['Volume fading at resistance'],
      },
    ],
    account: {
      equity: 100000, daily_realized_pnl: 420.00, daily_unrealized_pnl: 213.60,
      daily_total_pnl: 633.60, daily_loss_pct: 0.0, daily_loss_limit: 3.0,
      daily_loss_limit_used_pct: 0.0, open_positions: 2, max_positions: 4,
      exposure_pct: 14.2, max_exposure_pct: 30, consecutive_losses: 0, trades_today: 3,
    },
    performance: {
      setup_stats: {
        vwap_reclaim:    { trade_count: 18, win_rate: 0.667, avg_r: 1.21 },
        break_and_hold:  { trade_count: 12, win_rate: 0.583, avg_r: 0.94 },
        fibonacci_pullback: { trade_count: 7, win_rate: 0.714, avg_r: 1.55 },
        opening_range_breakout: { trade_count: 9, win_rate: 0.556, avg_r: 0.87 },
        bottom_base:     { trade_count: 5, win_rate: 0.600, avg_r: 1.10 },
      },
      equity_curve: Array.from({ length: 20 }, (_, i) => ({
        date: new Date(Date.now() - (19-i)*86400000).toLocaleDateString(),
        cumulative_r: parseFloat((Math.sin(i*0.4)*3 + i*0.3 + Math.random()*0.5).toFixed(2)),
        daily_r: parseFloat((Math.random()*2 - 0.5).toFixed(2)),
      })),
      today_trades: [
        { ticker: 'AMD', setup_type: 'vwap_reclaim', r_multiple: 1.8, realized_pnl: 324, exit_reason: 'First target hit' },
        { ticker: 'MARA', setup_type: 'break_and_hold', r_multiple: -1.0, realized_pnl: -96, exit_reason: 'Stop loss hit' },
        { ticker: 'PLTR', setup_type: 'fibonacci_pullback', r_multiple: 0.95, realized_pnl: 192, exit_reason: 'Time exit' },
      ],
    },
    rejections: [
      { ticker: 'TSLA', timestamp: new Date().toISOString(), reasons: ['Relative volume 1.4x below minimum 2x'], score_breakdown: {} },
      { ticker: 'RIVN', timestamp: new Date().toISOString(), reasons: ['Setup score 58 below minimum 65', 'Price below VWAP with lower highs'], score_breakdown: {} },
    ],
    control: {
      pause: () => console.log('pause'),
      resume: () => console.log('resume'),
      stop: () => console.log('stop'),
      emergencyClose: () => console.log('emergency close'),
      closePosition: (t) => console.log('close', t),
    },
    refresh: () => {},
  }
}
