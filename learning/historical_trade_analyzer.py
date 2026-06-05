"""
learning/historical_trade_analyzer.py — Analyzes closed trades for patterns
Reviews closed trades, identifies what factors predicted wins vs losses.
"""

import json
import logging
from pathlib import Path
from collections import defaultdict
from typing import Optional

log = logging.getLogger(__name__)


class HistoricalTradeAnalyzer:
    def __init__(self, settings: dict):
        self.settings = settings
        self.trade_dir = Path(settings["logging"]["trade_log_dir"])

    def load_all_trades(self) -> list[dict]:
        trades = []
        for path in sorted(self.trade_dir.glob("*.json")):
            try:
                with open(path) as f:
                    content = f.read()
                # Handle appended JSON records (separated by newlines)
                for block in content.strip().split("\n\n"):
                    if block.strip():
                        record = json.loads(block)
                        if record.get("event") == "EXIT":
                            trades.append(record)
            except Exception as exc:
                log.warning(f"Could not parse {path}: {exc}")
        return trades

    def analyze(self) -> dict:
        trades = self.load_all_trades()
        if not trades:
            return {"message": "No closed trades to analyze"}

        # Win/loss by setup type
        by_setup = defaultdict(lambda: {"wins": 0, "losses": 0, "r_total": 0.0, "trades": []})
        for t in trades:
            setup = t.get("setup_type", "unknown")
            r = t.get("r_multiple", 0)
            by_setup[setup]["trades"].append(t)
            by_setup[setup]["r_total"] += r
            if r > 0:
                by_setup[setup]["wins"] += 1
            else:
                by_setup[setup]["losses"] += 1

        setup_summary = {}
        for setup, data in by_setup.items():
            total = data["wins"] + data["losses"]
            setup_summary[setup] = {
                "total": total,
                "win_rate": round(data["wins"] / total, 3) if total else 0,
                "avg_r": round(data["r_total"] / total, 3) if total else 0,
            }

        # Winning trade patterns
        winners = [t for t in trades if t.get("r_multiple", 0) > 0]
        losers  = [t for t in trades if t.get("r_multiple", 0) <= 0]

        def avg_score(trade_list):
            scores = [t.get("setup_score", 0) for t in trade_list if t.get("setup_score")]
            return round(sum(scores) / len(scores), 1) if scores else 0

        return {
            "total_trades": len(trades),
            "winners": len(winners),
            "losers": len(losers),
            "overall_win_rate": round(len(winners) / len(trades), 3) if trades else 0,
            "avg_r_winners": round(sum(t.get("r_multiple", 0) for t in winners) / len(winners), 2) if winners else 0,
            "avg_r_losers":  round(sum(t.get("r_multiple", 0) for t in losers)  / len(losers),  2) if losers  else 0,
            "avg_setup_score_winners": avg_score(winners),
            "avg_setup_score_losers":  avg_score(losers),
            "by_setup": setup_summary,
        }

    def flag_underperforming_setups(self, min_trades: int = 10, min_win_rate: float = 0.4) -> list[str]:
        """Return setup types that have underperformed and should be reviewed."""
        analysis = self.analyze()
        flagged = []
        for setup, data in analysis.get("by_setup", {}).items():
            if data["total"] >= min_trades and data["win_rate"] < min_win_rate:
                flagged.append(setup)
                log.warning(f"Setup '{setup}' flagged for review: {data['win_rate']:.0%} WR over {data['total']} trades")
        return flagged
