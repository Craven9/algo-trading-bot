"""
setups/bottom_base.py — Bottom base / coil reversal setup
Detects: price builds a tight base at support after a down move.
"""

import logging
from .base_setup import BaseSetup, SetupResult

log = logging.getLogger(__name__)


class BottomBase(BaseSetup):
    @property
    def setup_name(self) -> str:
        return "bottom_base"

    def detect(self, bars: list[dict], indicators: dict, context: dict) -> SetupResult:
        if len(bars) < 20:
            return self._not_detected(["Insufficient bar data"])

        price = indicators.get("latest_close", 0)
        atr   = indicators.get("atr")
        vwap  = indicators.get("vwap")

        cfg = self.profile.get("entry", {})
        min_base_bars = cfg.get("require_base_bars", 3)
        max_base_range_pct = cfg.get("max_base_range_pct", 3.0)

        # Look for the base in the last 10 bars
        base_bars = bars[-10:]
        base_high = max(b["h"] for b in base_bars)
        base_low  = min(b["l"] for b in base_bars)
        base_range_pct = (base_high - base_low) / base_low * 100 if base_low else 99

        if base_range_pct > max_base_range_pct:
            return self._not_detected([f"Base range {base_range_pct:.1f}% too wide (max {max_base_range_pct}%)"])

        # Volume contraction during base
        if cfg.get("require_volume_contraction", True):
            recent_vols = [b["v"] for b in base_bars]
            avg_vol = sum(recent_vols) / len(recent_vols)
            prior_avg = sum(b["v"] for b in bars[-20:-10]) / 10
            vol_contracting = avg_vol < prior_avg * 0.8
            if not vol_contracting:
                return self._not_detected(["Volume not contracting during base formation"])

        # Price should be at or near a support level (swing low)
        swing_lows = indicators.get("swing_lows", [])
        near_support = any(abs(price - sl) / price < 0.02 for sl in swing_lows) if swing_lows else False

        # Breakout trigger: price at the top of the base range
        near_base_top = price >= base_high * 0.99

        if not near_base_top:
            return self._not_detected([f"Price ${price:.2f} not near base top ${base_high:.2f}"])

        stop_price = base_low * 0.99
        atr_val = atr or price * 0.02
        initial_target = price + atr_val * 2.0
        runner_target  = price + atr_val * 4.0
        targets = [initial_target, runner_target, price + atr_val * 6.0]

        confidence = 0.60
        if near_support:         confidence += 0.10
        if base_range_pct < 1.5: confidence += 0.10
        if indicators.get("higher_lows"): confidence += 0.05

        return SetupResult(
            detected=True,
            setup_type=self.setup_name,
            confidence=min(confidence, 1.0),
            entry_price=price,
            entry_zone_low=base_high * 0.99,
            entry_zone_high=base_high * 1.02,
            stop_price=stop_price,
            initial_target=initial_target,
            runner_target=runner_target,
            targets=targets,
            signals={
                "vwap_reclaim": False,
                "break_and_hold": False,
                "near_key_level": near_support,
                "failed_key_level": False,
                "liquidity_sweep_reclaim": False,
                "opening_range_status": context.get("setup_signal", {}).get("opening_range_status", "unknown"),
                "fib_proximity_pct": context.get("setup_signal", {}).get("fib_proximity_pct"),
            },
            description=f"Bottom base ${base_low:.2f}–${base_high:.2f} ({base_range_pct:.1f}% range) | Entry ${price:.2f} | Stop ${stop_price:.2f}",
        )
