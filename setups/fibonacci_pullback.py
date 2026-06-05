"""
setups/fibonacci_pullback.py — Fibonacci retracement pullback setup
Detects: price pulls back to a key Fib level after an impulsive move.
"""

import logging
from .base_setup import BaseSetup, SetupResult

log = logging.getLogger(__name__)


class FibonacciPullback(BaseSetup):
    @property
    def setup_name(self) -> str:
        return "fibonacci_pullback"

    def detect(self, bars: list[dict], indicators: dict, context: dict) -> SetupResult:
        if len(bars) < 20:
            return self._not_detected(["Insufficient bar data"])

        fib_result = context.get("fib_result")
        if not fib_result:
            return self._not_detected(["Fibonacci levels not calculated"])

        if not fib_result.in_entry_zone:
            prox = fib_result.proximity_pct
            return self._not_detected([
                f"Price not within entry zone of Fib level "
                f"({'%.1f' % prox}% away)" if prox else "Price far from Fib levels"
            ])

        # Only trade Fibonacci pullbacks in the direction of the trend
        if fib_result.direction != "up":
            return self._not_detected(["Fibonacci direction is down — no long setup"])

        price = indicators.get("latest_close", 0)
        atr   = indicators.get("atr")

        cfg = self.profile.get("entry", {})
        require_bounce = cfg.get("require_bounce_confirmation", True)

        # Bounce confirmation: current bar closes higher than prior bar
        if require_bounce and len(bars) >= 2:
            if bars[-1]["c"] <= bars[-2]["c"]:
                return self._not_detected(["No bounce confirmation — current bar closing lower"])

        stop_price = fib_result.retracements.get(0.786, fib_result.swing_low) * 0.995
        targets = fib_result.targets or []
        initial_target = targets[0] if targets else price + (atr or price * 0.02) * 2
        runner_target  = targets[1] if len(targets) > 1 else initial_target * 1.02

        confidence = 0.65
        prox = fib_result.proximity_pct or 99
        if prox <= 0.5:  confidence += 0.15
        elif prox <= 1:  confidence += 0.08
        if indicators.get("higher_lows"): confidence += 0.08
        level = fib_result.nearest_retracement_level
        if level in [0.382, 0.5, 0.618]: confidence += 0.05

        level_str = f"{(level or 0)*100:.1f}%" if level else "?"
        return SetupResult(
            detected=True,
            setup_type=self.setup_name,
            confidence=min(confidence, 1.0),
            entry_price=price,
            entry_zone_low=fib_result.nearest_retracement * 0.98 if fib_result.nearest_retracement else None,
            entry_zone_high=fib_result.nearest_retracement * 1.02 if fib_result.nearest_retracement else None,
            stop_price=stop_price,
            initial_target=initial_target,
            runner_target=runner_target,
            targets=targets,
            signals={
                "vwap_reclaim": False,
                "break_and_hold": False,
                "near_key_level": True,
                "failed_key_level": False,
                "liquidity_sweep_reclaim": context.get("setup_signal", {}).get("liquidity_sweep_reclaim", False),
                "opening_range_status": context.get("setup_signal", {}).get("opening_range_status", "unknown"),
                "fib_proximity_pct": prox,
            },
            description=f"Fib pullback to {level_str} at ${fib_result.nearest_retracement:.2f} | {prox:.1f}% away | Entry ${price:.2f} | Stop ${stop_price:.2f}",
        )
