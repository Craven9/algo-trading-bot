"""
analysis/move_potential_engine.py — Estimates realistic upside and R:R
Uses ATR, resistance levels, and Fibonacci extensions to project targets.
"""

import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class MovePotentialResult:
    entry_price: float
    stop_price: float
    stop_distance: float
    stop_distance_pct: float
    initial_target: float
    runner_target: float
    max_target: float
    risk_reward: float
    risk_reward_at_runner: float
    passes_rr_minimum: bool
    atr: Optional[float]


class MovePotentialEngine:
    def __init__(self, settings: dict):
        self.settings = settings
        self.min_rr = settings["entry"]["min_risk_reward"]
        self.preferred_rr = settings["entry"]["preferred_risk_reward"]

    def calculate(
        self,
        entry_price: float,
        stop_price: float,
        targets: list[float],
        atr: Optional[float] = None,
    ) -> MovePotentialResult:
        """
        Calculate stop distance, R:R, and classify target quality.
        Targets should be ordered from nearest to furthest.
        """
        stop_distance = entry_price - stop_price
        stop_distance_pct = (stop_distance / entry_price * 100) if entry_price > 0 else 0

        if not targets:
            # Fall back to ATR-based targets
            targets = self._atr_targets(entry_price, stop_distance, atr)

        initial_target = targets[0] if targets else entry_price + stop_distance * 1.5
        runner_target = targets[1] if len(targets) > 1 else initial_target
        max_target = targets[-1] if targets else initial_target

        rr_initial = (initial_target - entry_price) / stop_distance if stop_distance > 0 else 0
        rr_runner = (runner_target - entry_price) / stop_distance if stop_distance > 0 else 0

        return MovePotentialResult(
            entry_price=entry_price,
            stop_price=stop_price,
            stop_distance=round(stop_distance, 4),
            stop_distance_pct=round(stop_distance_pct, 2),
            initial_target=round(initial_target, 4),
            runner_target=round(runner_target, 4),
            max_target=round(max_target, 4),
            risk_reward=round(rr_initial, 2),
            risk_reward_at_runner=round(rr_runner, 2),
            passes_rr_minimum=rr_initial >= self.min_rr,
            atr=atr,
        )

    def _atr_targets(self, entry: float, stop_distance: float, atr: Optional[float]) -> list[float]:
        """Generate ATR-based targets when Fibonacci targets aren't available."""
        unit = atr or stop_distance
        return [
            entry + unit * 1.5,
            entry + unit * 2.5,
            entry + unit * 4.0,
        ]

    def calculate_stop(self, bars: list[dict], entry_price: float, atr: Optional[float]) -> float:
        """
        Calculate the structural stop — below the most recent swing low,
        with ATR as a minimum stop distance sanity check.
        """
        swing_lows = [b["l"] for b in bars[-10:] if b["l"] < entry_price]
        if swing_lows:
            structural_stop = min(swing_lows)
        else:
            structural_stop = entry_price - (atr or entry_price * 0.02)

        # Ensure stop is at least 0.5× ATR away (not too tight)
        if atr:
            min_stop = entry_price - atr * 0.5
            structural_stop = min(structural_stop, min_stop)

        return round(structural_stop, 4)
