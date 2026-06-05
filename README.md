# Algo Trading Bot

A disciplined, fully-explained algorithmic paper trading bot for intraday momentum setups. Built around the principle: **the bot is a filter, not a buyer.** Every stock passes through progressively stricter gates, and most get rejected at each one.

---

## Architecture Overview

```
Scanner → Analysis → Decision Gate → Risk → Execution → Exit → Learning
                                                              ↑
                                                         Feedback loop
```

Every decision is logged with a full explanation. Every rejection is stored and reviewable. Nothing makes trade decisions except `trade_quality_gate.py`.

---

## Supported Setups

| Setup | Description |
|-------|-------------|
| **Break & Hold** | Price breaks a key level, pulls back, and holds above it |
| **VWAP Reclaim** | Price dips below VWAP, reclaims it with volume confirmation |
| **Bottom Base** | Price coils in a tight base at support, then breaks out |
| **Fibonacci Pullback** | Price retraces to 38.2%, 50%, or 61.8% then bounces |
| **Opening Range Breakout** | Price breaks the ORH with volume after the first 15 minutes |

---

## Quick Start

### 1. Clone and set up Python environment

```bash
git clone https://github.com/YOUR_USERNAME/algo-trading-bot.git
cd algo-trading-bot
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure API keys

```bash
cp .env.example .env
# Edit .env and add your Polygon.io and Alpaca API keys
```

**Get your keys:**
- **Polygon.io** (market data): https://polygon.io — free tier available
- **Alpaca** (paper trading): https://alpaca.markets — free paper trading account

### 3. Start the bot (dry run mode)

```bash
python bot_runner.py
```

The bot starts in **dry run mode** by default — no orders are placed. Watch the logs to see the scanner and analysis pipeline in action.

### 4. Start the React dashboard

```bash
cd frontend/dashboard
npm install
npm run dev
# Open http://localhost:3000
```

---

## Configuration

All settings live in `config/bot_settings.json`. Key sections:

```json
{
  "mode": {
    "dry_run": true,         ← Start here. No orders placed.
    "paper_trading": true,   ← Paper orders via Alpaca
    "live_trading": false    ← Never enable until confident
  },
  "risk": {
    "risk_per_trade_pct": 1.0,    ← 1% of account per trade
    "daily_loss_limit_pct": 3.0,  ← Bot stops at 3% daily loss
    "max_open_positions": 4
  },
  "entry": {
    "min_setup_score": 65,   ← Quality gate minimum
    "min_probability": 55,   ← Probability minimum
    "min_risk_reward": 2.0   ← R:R minimum
  }
}
```

Per-setup tuning is in `config/strategy_profiles.json`.

---

## Decision Flow (7 phases)

1. **Fast screen** — Relative volume, price range, float
2. **Technical analysis** — VWAP, RSI, MACD, ATR, structure
3. **Setup detection** — Identify which setup pattern applies
4. **Scoring** — 0–100 score from 10 weighted factors
5. **Probability** — Historical win rate + market conditions
6. **Risk/Reward** — Must be ≥ 2:1 minimum
7. **Position sizing** — Account risk % ÷ stop distance

Any phase can reject a trade with a full reason logged.

---

## Scoring Factors (0–100)

| Factor | Max Points |
|--------|-----------|
| VWAP position / reclaim quality | 15 |
| Key level behavior | 15 |
| Volume confirmation (rel. vol.) | 15 |
| Market structure (higher lows) | 10 |
| RSI momentum | 10 |
| MACD signal | 8 |
| Fibonacci proximity | 8 |
| Opening range status | 8 |
| Liquidity sweep reclaim | 7 |
| Catalyst / news quality | 4 |

**Minimum to proceed: 65/100. Strong setup: 75+.**

---

## Exit Rules (in priority order)

1. **Hard stop** — Structural stop below entry (non-negotiable)
2. **Failed breakout** — Bull trap detected
3. **VWAP loss** — For VWAP setups: price loses VWAP with volume
4. **Break-even** — Stop moved to entry after 1R profit
5. **First partial** — Take 40% off at 1.5R
6. **Volume fade** — Exit runner if volume collapses at resistance
7. **Fibonacci extensions** — 1.272 / 1.618 / 2.0 / 2.618 targets
8. **Trailing stop** — Under most recent higher low (5m)
9. **EOD exit** — All positions closed 15 minutes before close

---

## Project Structure

```
algo-trading-bot/
├── bot_runner.py              ← Master orchestrator
├── config/
│   ├── bot_settings.json      ← All configuration
│   └── strategy_profiles.json ← Per-setup tuning
├── data/                      ← Polygon.io data layer
├── scanner/                   ← Momentum candidate scanning
├── analysis/                  ← Technical analysis engines
├── setups/                    ← Setup pattern detectors
├── decision/                  ← Trade quality gate
├── risk/                      ← Position sizing & limits
├── execution/                 ← Alpaca order management
├── exit/                      ← Exit logic
├── learning/                  ← Performance tracking
├── frontend/
│   ├── api_server.py          ← FastAPI backend
│   └── dashboard/             ← React dashboard
└── logs/
    ├── trades/                ← One JSON per trade
    ├── rejections/            ← Every rejected ticker
    └── performance/           ← Daily summaries
```

---

## Build Roadmap

| Week | Focus |
|------|-------|
| 1 | Finalize config, data fetcher, base setup interface |
| 2 | Setup score engine, Fibonacci engine |
| 3 | Trade quality gate, rejection logging, dry run pipeline |
| 4 | Risk manager, account guard, Alpaca paper orders |
| 5 | Exit manager, full entry-to-exit lifecycle |
| 6 | Performance tracker, probability engine feedback loop |
| 7 | Dashboard panels, live data, controls |
| 8 | Paper trading week, review, weight tuning |

---

## Risk Warnings

- **Paper trade first.** Run the bot in dry run, then paper mode, for at least 4–8 weeks before considering live trading.
- **Never risk money you can't afford to lose.** Algorithmic trading carries significant risk of loss.
- **Past performance of any strategy does not guarantee future results.**
- **This bot is educational.** It is not investment advice.

---

## Dashboard

The React dashboard has 5 panels:
- **Status bar** — Mode, session, P&L, risk used, controls
- **Account** — Equity, exposure, streak, trades today  
- **Open Positions** — Live P&L, R multiples, stop levels, exit warnings
- **Performance** — Equity curve, win rate by setup, closed trades
- **Rejections** — Every rejected ticker with full reason breakdown

---

## License

MIT — use freely, at your own risk.
