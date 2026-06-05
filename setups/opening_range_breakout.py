"""
setups/opening_range_breakout.py — Opening range breakout setup
Detects: price breaks the ORH with volume after the first N minutes.
"""

import logging
from .base_setup import BaseSetup, SetupResult
from analysis.opening_range_analyzer import OpeningRangeAnalyzer

log = logging.getLogger(__name__)


class OpeningRangeBreakout(BaseSetup):
    @property
    def setup_name(self) -> str:
        return "opening_range_breakout"

    def detect(self, bars: list[dict], indicators: dict, context: dict) -> SetupResult:
        if len(bars) < 10:
            return self._not_detected(["Insufficient bar data"])

        or_analyzer = OpeningRangeAnalyzer(self.settings)
        or_range = or_analyzer.get_opening_range(bars)

        if not or_range or not or_range.formed:
            return self._not_detected(["Opening range not yet formed"])

        cfg = self.profile.get("entry", {})
        min_range_pct = cfg.get("min_or_range_pct", 0.5)
        if or_range.range_pct < min_range_pct:
            return self._not_detected([f"OR range {or_range.range_pct:.1f}% too tight (min {min_range_pct}%)"])

        price = indicators.get("latest_close", 0)
        atr   = indicators.get("atr")
        rv    = indicators.get("relative_volume", 0)

        # Condition: price has broken above ORH
        if price <= or_range.high:
            return self._not_detected([f"Price ${price:.2f} has not broken ORH ${or_range.high:.2f}"])

        # Condition: not too extended above ORH
        max_above_pct = cfg.get("max_entry_above_orh_pct", 2.0)
        dist_pct = (price - or_range.high) / or_range.high * 100
        if dist_pct > max_above_pct:
            return self._not_detected([f"Price {dist_pct:.1f}% above ORH — too extended"])

        # Condition: volume on the breakout
        require_vol = cfg.get("require_volume_on_break", True)
        if require_vol and rv < 2.0:
            return self._not_detected([f"Relative volume {rv:.1f}x insufficient for ORB confirmation"])

        # Stop: below ORH (not below ORL — that's too far)
        stop_price = or_range.high * 0.99

        atr_val = atr or price * 0.02
        initial_target = price + atr_val * 1.5
        runner_target  = price + atr_val * 3.0
        targets = [initial_target, runner_target, price + atr_val * 5.0]

        confidence = 0.65
        if rv >= 3.0: confidence += 0.10
        if indicators.get("higher_lows"): confidence += 0.05
        if or_range.range_pct >= 2.0: confidence += 0.05
        if indicators.get("vwap") and price > indicators["vwap"]: confidence += 0.05

        or_status = or_analyzer.get_or_status(bars, price)

        return SetupResult(
            detected=True,
            setup_type=self.setup_name,
            confidence=min(confidence, 1.0),
            entry_price=price,
            entry_zone_low=or_range.high,
            entry_zone_high=or_range.high * (1 + max_above_pct / 100),
            stop_price=stop_price,
            initial_target=initial_target,
            runner_target=runner_target,
            targets=targets,
            signals={
                "vwap_reclaim": False,
                "break_and_hold": True,
                "near_key_level": True,
                "failed_key_level": False,
                "liquidity_sweep_reclaim": False,
                "opening_range_status": or_status,
                "fib_proximity_pct": context.get("setup_signal", {}).get("fib_proximity_pct"),
            },
            description=f"ORB above ${or_range.high:.2f} | OR range {or_range.range_pct:.1f}% | RV {rv:.1f}x | Entry ${price:.2f} | Stop ${stop_price:.2f}",
        )
