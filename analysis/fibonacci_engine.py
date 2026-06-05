"""
analysis/fibonacci_engine.py — Fibonacci retracement and extension calculator
Identifies swing points, calculates key levels, confirms entry proximity.
"""

import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

RETRACEMENT_LEVELS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
EXTENSION_LEVELS   = [1.0, 1.272, 1.618, 2.0, 2.618]


@dataclass
class FibonacciResult:
    swing_high: float
    swing_low: float
    direction: str           # "up" or "down"
    retracements: dict       # level → price
    extensions: dict         # level → price
    nearest_retracement: Optional[float]
    nearest_retracement_level: Optional[float]
    proximity_pct: Optional[float]
    in_entry_zone: bool
    targets: list[float]     # extension prices in order


class FibonacciEngine:
    def __init__(self, settings: dict):
        self.cfg = settings.get("fibonacci", {})
        self.preferred_retracements = self.cfg.get("preferred_retracements", [0.382, 0.5, 0.618])
        self.preferred_extensions = self.cfg.get("preferred_extensions", [1.272, 1.618, 2.0, 2.618])
        self.max_distance_pct = self.cfg.get("max_distance_from_level_pct", 2.0)

    def calculate(self, bars: list[dict], current_price: float) -> Optional[FibonacciResult]:
        """
        Find the most recent significant swing, calculate retracements and extensions,
        and determine if current price is in a preferred entry zone.
        """
        if len(bars) < 20:
            return None

        high, low, direction = self._find_swing(bars)
        if high is None or low is None:
            return None

        retrace = self._calc_retracements(high, low, direction)
        extensions = self._calc_extensions(high, low, direction)

        # Find nearest preferred retracement to current price
        nearest_level = None
        nearest_price = None
        nearest_dist = float("inf")

        for lvl in self.preferred_retracements:
            price = retrace.get(lvl)
            if price is None:
                continue
            dist = abs(current_price - price) / current_price * 100
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_level = lvl
                nearest_price = price

        in_zone = nearest_dist <= self.max_distance_pct if nearest_dist < float("inf") else False

        # Build target list from extension levels in direction of trade
        targets = [extensions[lvl] for lvl in self.preferred_extensions if lvl in extensions]

        return FibonacciResult(
            swing_high=high,
            swing_low=low,
            direction=direction,
            retracements=retrace,
            extensions=extensions,
            nearest_retracement=nearest_price,
            nearest_retracement_level=nearest_level,
            proximity_pct=round(nearest_dist, 2) if nearest_dist < float("inf") else None,
            in_entry_zone=in_zone,
            targets=targets,
        )

    def _find_swing(self, bars: list[dict]) -> tuple:
        """
        Identify the most recent impulsive move.
        Returns (swing_high, swing_low, direction).
        """
        lookback = min(50, len(bars))
        recent = bars[-lookback:]

        # Find the highest high and lowest low in the lookback
        high_idx = max(range(len(recent)), key=lambda i: recent[i]["h"])
        low_idx  = min(range(len(recent)), key=lambda i: recent[i]["l"])

        swing_high = recent[high_idx]["h"]
        swing_low  = recent[low_idx]["l"]

        # Direction = which came first
        if high_idx > low_idx:
            direction = "up"   # low formed first, then high → uptrend, look for pullback to retracement
        else:
            direction = "down" # high formed first, then low

        return swing_high, swing_low, direction

    def _calc_retracements(self, high: float, low: float, direction: str) -> dict:
        rng = high - low
        result = {}
        for lvl in RETRACEMENT_LEVELS:
            if direction == "up":
                result[lvl] = high - rng * lvl   # 0% = high, 100% = low
            else:
                result[lvl] = low + rng * lvl    # 0% = low, 100% = high
        return result

    def _calc_extensions(self, high: float, low: float, direction: str) -> dict:
        rng = high - low
        result = {}
        for lvl in EXTENSION_LEVELS:
            if direction == "up":
                result[lvl] = low + rng * lvl    # extensions beyond the high
            else:
                result[lvl] = high - rng * lvl   # extensions beyond the low
        return result

    def get_runner_targets(self, fib: FibonacciResult) -> list[dict]:
        """Return extension levels as named targets for the exit manager."""
        names = {1.272: "First Extension", 1.618: "Main Target", 2.0: "Extended", 2.618: "Max Extension"}
        targets = []
        for lvl, price in fib.extensions.items():
            if lvl in self.preferred_extensions:
                targets.append({
                    "level": lvl,
                    "price": price,
                    "name": names.get(lvl, f"{lvl:.3f} Extension"),
                })
        return sorted(targets, key=lambda t: t["price"] if fib.direction == "up" else -t["price"])
