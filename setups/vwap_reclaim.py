"""
setups/vwap_reclaim.py — VWAP reclaim setup
Detects: price dips below VWAP, then reclaims it with volume confirmation.
"""

import logging
from .base_setup import BaseSetup, SetupResult

log = logging.getLogger(__name__)


class VWAPReclaim(BaseSetup):
    @property
    def setup_name(self) -> str:
        return "vwap_reclaim"

    def detect(self, bars: list[dict], indicators: dict, context: dict) -> SetupResult:
        if len(bars) < 10:
            return self._not_detected(["Insufficient bar data"])

        vwap  = indicators.get("vwap")
        price = indicators.get("latest_close", 0)
        atr   = indicators.get("atr")
        rv    = indicators.get("relative_volume", 0)

        if not vwap:
            return self._not_detected(["VWAP not available"])

        # Condition 1: price is currently above VWAP
        if price <= vwap:
            return self._not_detected([f"Price ${price:.2f} still below VWAP ${vwap:.2f}"])

        # Condition 2: at least one of the last 5 bars had a close below VWAP (the dip)
        recent_bars = bars[-6:-1]  # exclude current bar
        dipped_below = any(b["c"] < vwap for b in recent_bars)
        if not dipped_below:
            return self._not_detected(["No recent dip below VWAP — not a reclaim pattern"])

        # Condition 3: the reclaim bar (most recent) closed above VWAP
        reclaim_bar = bars[-1]
        if reclaim_bar["c"] <= vwap:
            return self._not_detected(["Current bar has not closed above VWAP"])

        # Condition 4: volume surge on the reclaim bar
        require_volume = self.profile.get("entry", {}).get("require_volume_surge", True)
        if require_volume and rv < 1.5:
            return self._not_detected([f"Relative volume {rv:.1f}x too low for reclaim confirmation"])

        # Condition 5: not an overextended reclaim (price not more than X% above VWAP)
        max_above_pct = self.profile.get("entry", {}).get("max_entry_above_vwap_pct", 1.5)
        dist_pct = (price - vwap) / vwap * 100
        if dist_pct > max_above_pct:
            return self._not_detected([f"Price {dist_pct:.1f}% above VWAP — too extended from reclaim"])

        # Stop: below VWAP (the thesis is VWAP holds as support)
        stop_price = vwap * 0.995

        # Targets
        atr_val = atr or price * 0.02
        initial_target = price + atr_val * 1.5
        runner_target  = price + atr_val * 3.0
        targets = [initial_target, runner_target, price + atr_val * 5.0]

        # Check for liquidity sweep before the reclaim (sweeps make reclaims more powerful)
        sweep_bars = bars[-8:-1]
        swept_below = any(b["l"] < vwap * 0.995 and b["c"] > vwap for b in sweep_bars)

        confidence = 0.65
        if rv >= 2.0:    confidence += 0.10
        if rv >= 3.0:    confidence += 0.05
        if swept_below:  confidence += 0.10
        if indicators.get("higher_lows"): confidence += 0.05

        return SetupResult(
            detected=True,
            setup_type=self.setup_name,
            confidence=min(confidence, 1.0),
            entry_price=price,
            entry_zone_low=vwap,
            entry_zone_high=vwap * (1 + max_above_pct / 100),
            stop_price=stop_price,
            initial_target=initial_target,
            runner_target=runner_target,
            targets=targets,
            signals={
                "vwap_reclaim": True,
                "break_and_hold": False,
                "near_key_level": True,
                "failed_key_level": False,
                "liquidity_sweep_reclaim": swept_below,
                "opening_range_status": context.get("setup_signal", {}).get("opening_range_status", "unknown"),
                "fib_proximity_pct": context.get("setup_signal", {}).get("fib_proximity_pct"),
            },
            description=f"VWAP reclaim at ${vwap:.2f} | RV {rv:.1f}x | {'swept first' if swept_below else 'clean reclaim'} | Entry ${price:.2f} | Stop ${stop_price:.2f}",
        )
