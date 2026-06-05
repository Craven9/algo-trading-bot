"""
analysis/probability_engine.py — Estimates trade success probability
Combines setup score, market conditions, and historical bot performance.
All probability history is sourced from performance_tracker.py.
"""

import logging
from typing import Optional

log = logging.getLogger(__name__)


class ProbabilityEngine:
    """
    Produces a probability estimate (0.0–1.0) for a given setup.

    Base rate comes from the setup score (normalized to a rough probability).
    Adjustments come from:
      - Historical win rate for this setup type (from performance_tracker)
      - Market condition (trending / choppy / strong downtrend)
      - Time of day
      - Sector strength
      - Relative volume multiplier
    """

    def __init__(self, settings: dict, performance_tracker=None):
        self.settings = settings
        self.perf = performance_tracker
        self.use_history = settings["learning"]["use_historical_win_rate_in_probability"]
        self.min_trades = settings["learning"]["min_trades_for_historical_adjustment"]

    def estimate(self, setup_score: float, context: dict, setup_type: str) -> dict:
        """
        Returns a dict with:
          probability: float (0.0 – 1.0)
          base_probability: float
          adjustments: list of {name, delta, reason}
          confidence: str (low / medium / high)
        """
        adjustments = []

        # Base: map setup score (0–100) to base probability range (0.35–0.75)
        # Score 65 → ~0.52, Score 80 → ~0.60, Score 95 → ~0.70
        base = 0.35 + (setup_score / 100) * 0.40
        adjustments.append({"name": "Setup Score Base", "delta": base, "reason": f"Score {setup_score:.0f}/100"})

        # Historical win rate adjustment
        if self.use_history and self.perf:
            stats = self.perf.get_setup_stats(setup_type)
            if stats and stats.get("trade_count", 0) >= self.min_trades:
                hist_wr = stats["win_rate"]
                delta = (hist_wr - 0.5) * 0.3  # scale: 60% WR → +0.03
                adjustments.append({
                    "name": "Historical Win Rate",
                    "delta": delta,
                    "reason": f"{setup_type} historical WR: {hist_wr:.0%} over {stats['trade_count']} trades"
                })

        # Market condition
        market_state = context.get("market_state", {})
        market_bias = market_state.get("bias", "neutral")
        if market_bias == "bullish":
            adjustments.append({"name": "Market Condition", "delta": 0.05, "reason": "Broad market bullish"})
        elif market_bias == "bearish":
            adjustments.append({"name": "Market Condition", "delta": -0.10, "reason": "Broad market bearish"})
        elif market_bias == "choppy":
            adjustments.append({"name": "Market Condition", "delta": -0.07, "reason": "Choppy/directionless market"})

        # VIX adjustment
        vix = market_state.get("vix", 20)
        if vix and vix > 30:
            delta = -0.05 * ((vix - 30) / 10)
            adjustments.append({"name": "High VIX", "delta": delta, "reason": f"Elevated VIX {vix:.0f}"})

        # Time of day
        session = context.get("session", "ACTIVE")
        if session == "OPENING":
            adjustments.append({"name": "Time of Day", "delta": -0.08, "reason": "First 30 minutes — high volatility"})
        elif session == "LUNCH":
            adjustments.append({"name": "Time of Day", "delta": -0.05, "reason": "Lunch hour — low volume"})

        # Relative volume boost
        rv = context.get("ohlcv", {}).get("relative_volume", 1.0)
        if rv >= 3.0:
            adjustments.append({"name": "Relative Volume", "delta": 0.03, "reason": f"Strong relative volume {rv:.1f}x"})
        elif rv < 1.5:
            adjustments.append({"name": "Relative Volume", "delta": -0.05, "reason": f"Low relative volume {rv:.1f}x"})

        # Catalyst boost
        if context.get("news", {}).get("has_catalyst"):
            adjustments.append({"name": "Catalyst", "delta": 0.04, "reason": "Confirmed catalyst present"})

        # Sum all adjustments (skip the base, which is already included)
        total = base + sum(a["delta"] for a in adjustments[1:])
        probability = max(0.0, min(1.0, total))

        # Confidence based on historical data availability
        if self.perf and self.perf.get_setup_stats(setup_type, {}).get("trade_count", 0) >= 20:
            confidence = "high"
        elif self.perf and self.perf.get_setup_stats(setup_type, {}).get("trade_count", 0) >= self.min_trades:
            confidence = "medium"
        else:
            confidence = "low"

        return {
            "probability": round(probability, 3),
            "probability_pct": round(probability * 100, 1),
            "base_probability": round(base, 3),
            "adjustments": adjustments,
            "confidence": confidence,
            "passes_threshold": probability >= (self.settings["entry"]["min_probability"] / 100),
        }
