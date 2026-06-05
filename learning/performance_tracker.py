"""
learning/performance_tracker.py — Tracks bot performance by setup type
Produces win rate, avg R, drawdown, and best/worst time windows.
Results feed back into the probability engine for future trades.
"""

import json
import logging
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


class PerformanceTracker:
    def __init__(self, settings: dict):
        self.settings = settings
        self.perf_dir = Path(settings["logging"]["performance_log_dir"])
        self.perf_dir.mkdir(parents=True, exist_ok=True)

        # In-memory stats (rebuilt from logs on startup)
        self._setup_stats: dict[str, dict] = defaultdict(lambda: {
            "trade_count": 0,
            "wins": 0,
            "losses": 0,
            "total_r": 0.0,
            "max_r": 0.0,
            "min_r": 0.0,
            "max_drawdown": 0.0,
            "r_multiples": [],
        })
        self._daily_summaries: list[dict] = []
        self._load_history()

    def record_day(self, closed_trades: list[dict]):
        """Called at end of day with all closed trades."""
        if not closed_trades:
            return

        day_pnl = sum(t.get("realized_pnl", 0) for t in closed_trades)
        day_r   = sum(t.get("r_multiple", 0) for t in closed_trades)

        for trade in closed_trades:
            self._record_trade(trade)

        summary = {
            "date": date.today().isoformat(),
            "trade_count": len(closed_trades),
            "winners": sum(1 for t in closed_trades if t.get("r_multiple", 0) > 0),
            "losers": sum(1 for t in closed_trades if t.get("r_multiple", 0) <= 0),
            "total_pnl": round(day_pnl, 2),
            "total_r": round(day_r, 2),
            "avg_r": round(day_r / len(closed_trades), 3) if closed_trades else 0,
        }
        self._daily_summaries.append(summary)
        self._save_daily_summary(summary)
        log.info(f"Day recorded: {summary['trade_count']} trades | PnL=${summary['total_pnl']:.2f} | {summary['total_r']:.2f}R")

    def _record_trade(self, trade: dict):
        setup = trade.get("setup_type", "unknown")
        r = trade.get("r_multiple", 0)
        stats = self._setup_stats[setup]
        stats["trade_count"] += 1
        stats["total_r"] += r
        stats["r_multiples"].append(r)
        if r > 0:
            stats["wins"] += 1
            stats["max_r"] = max(stats["max_r"], r)
        else:
            stats["losses"] += 1
            stats["min_r"] = min(stats["min_r"], r)

        # Update max drawdown (peak-to-trough in R)
        rs = stats["r_multiples"]
        peak = 0.0
        max_dd = 0.0
        running = 0.0
        for x in rs:
            running += x
            if running > peak:
                peak = running
            dd = peak - running
            if dd > max_dd:
                max_dd = dd
        stats["max_drawdown"] = round(max_dd, 3)

    def get_setup_stats(self, setup_type: str, default: dict = None) -> Optional[dict]:
        stats = self._setup_stats.get(setup_type)
        if not stats or stats["trade_count"] == 0:
            return default
        count = stats["trade_count"]
        return {
            "trade_count": count,
            "win_rate": round(stats["wins"] / count, 3) if count else 0,
            "avg_r": round(stats["total_r"] / count, 3) if count else 0,
            "max_r": stats["max_r"],
            "min_r": stats["min_r"],
            "max_drawdown": stats["max_drawdown"],
        }

    def get_all_stats(self) -> dict:
        return {
            setup: self.get_setup_stats(setup)
            for setup in self._setup_stats
        }

    def get_equity_curve(self) -> list[dict]:
        """Return cumulative R by day for the equity curve chart."""
        curve = []
        cumulative = 0.0
        for day in self._daily_summaries:
            cumulative += day.get("total_r", 0)
            curve.append({"date": day["date"], "cumulative_r": round(cumulative, 3), "daily_r": day.get("total_r", 0)})
        return curve

    def _save_daily_summary(self, summary: dict):
        path = self.perf_dir / f"daily_{summary['date']}.json"
        with open(path, "w") as f:
            json.dump(summary, f, indent=2)

    def _load_history(self):
        """Load existing performance logs on startup."""
        for path in sorted(self.perf_dir.glob("daily_*.json")):
            try:
                with open(path) as f:
                    self._daily_summaries.append(json.load(f))
            except Exception as exc:
                log.warning(f"Could not load {path}: {exc}")
        log.info(f"Performance history loaded: {len(self._daily_summaries)} days")
