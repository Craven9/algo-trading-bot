"""
setups/break_and_hold.py — Break and hold above a key level
Detects: price breaks a resistance level, pulls back to it, and holds above.
"""

import logging
from .base_setup import BaseSetup, SetupResult

log = logging.getLogger(__name__)


class BreakAndHold(BaseSetup):
    @property
    def setup_name(self) -> str:
        return "break_and_hold"

    def detect(self, bars: list[dict], indicators: dict, context: dict) -> SetupResult:
        if len(bars) < 15:
            return self._not_detected(["Insufficient bar data"])

        price = indicators.get("latest_close", 0)
        vwap  = indicators.get("vwap")
        atr   = indicators.get("atr")
        swing_highs = indicators.get("swing_highs", [])

        if not swing_highs:
            return self._not_detected(["No swing highs identified for key level"])

        # The key level is the most recent prior swing high
        key_level = swing_highs[-2] if len(swing_highs) >= 2 else swing_highs[-1]

        # Condition 1: price has broken above the key level
        if price <= key_level:
            return self._not_detected([f"Price ${price:.2f} has not broken above key level ${key_level:.2f}"])

        # Condition 2: the break happened recently (within last 5 bars)
        break_bars = [b for b in bars[-5:] if b["c"] > key_level]
        if not break_bars:
            return self._not_detected(["No recent break above key level in last 5 bars"])

        # Condition 3: price is holding above the level (no close back under it)
        recent_closes = [b["c"] for b in bars[-3:]]
        failed_reclaim = any(c < key_level for c in recent_closes)
        if failed_reclaim:
            return self._not_detected(["Failed break — price closed back under key level"])

        # Condition 4: holding for at least 2 bars
        hold_bars = sum(1 for b in bars[-5:] if b["l"] >= key_level * 0.998)  # small tolerance
        min_hold = self.profile.get("entry", {}).get("min_hold_bars", 2)
        if hold_bars < min_hold:
            return self._not_detected([f"Only {hold_bars} holding bars above level, need {min_hold}"])

        # Entry zone: current price up to 2% above the level
        entry_price = price
        max_entry_pct = self.profile.get("entry", {}).get("max_entry_above_breakout_pct", 2.0)
        max_entry = key_level * (1 + max_entry_pct / 100)
        if price > max_entry:
            return self._not_detected([f"Price {((price - key_level)/key_level*100):.1f}% above level — too extended to chase"])

        # Stop: below the key level (or below the nearest swing low under it)
        stop_price = key_level * 0.99  # 1% below the key level

        # Targets: ATR-based extensions
        atr_val = atr or (price * 0.02)
        initial_target = price + atr_val * 1.5
        runner_target  = price + atr_val * 3.0
        targets = [initial_target, runner_target, price + atr_val * 5.0]

        confidence = 0.7
        if indicators.get("higher_lows"):
            confidence += 0.1
        if indicators.get("vwap") and price > indicators["vwap"]:
            confidence += 0.1
        if hold_bars >= 3:
            confidence += 0.05

        return SetupResult(
            detected=True,
            setup_type=self.setup_name,
            confidence=min(confidence, 1.0),
            entry_price=entry_price,
            entry_zone_low=key_level,
            entry_zone_high=max_entry,
            stop_price=stop_price,
            initial_target=initial_target,
            runner_target=runner_target,
            targets=targets,
            signals={
                "break_and_hold": True,
                "vwap_reclaim": False,
                "near_key_level": True,
                "failed_key_level": False,
                "liquidity_sweep_reclaim": context.get("setup_signal", {}).get("liquidity_sweep_reclaim", False),
                "opening_range_status": context.get("setup_signal", {}).get("opening_range_status", "unknown"),
                "fib_proximity_pct": context.get("setup_signal", {}).get("fib_proximity_pct"),
            },
            description=f"Break and hold above ${key_level:.2f} | {hold_bars} bars holding | Entry ${entry_price:.2f} | Stop ${stop_price:.2f}",
        )
