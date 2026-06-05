"""
analysis/liquidity_sweep_detector.py — Detects stop hunts and reclaims
A liquidity sweep is a wick below a key support level followed by a close back above it.
"""

import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class SweepResult:
    detected: bool
    swept_level: Optional[float]
    reclaimed: bool
    sweep_bar_idx: Optional[int]
    wick_size_pct: Optional[float]
    description: str


class LiquiditySweepDetector:
    def __init__(self, settings: dict):
        self.settings = settings
        self.min_wick_pct = 0.3    # minimum wick size as % of price
        self.max_bars_to_reclaim = 5

    def detect(self, bars: list[dict], key_levels: list[float]) -> SweepResult:
        """
        Check the most recent bars for a liquidity sweep below a key level.
        Returns a SweepResult with detection details.
        """
        if len(bars) < 5 or not key_levels:
            return SweepResult(False, None, False, None, None, "Insufficient data")

        # Check the last 10 bars for sweep patterns
        recent = bars[-10:]
        current_close = bars[-1]["c"]

        for level in sorted(key_levels):
            result = self._check_sweep_at_level(recent, level, current_close)
            if result.detected:
                return result

        return SweepResult(False, None, False, None, None, "No sweep detected")

    def _check_sweep_at_level(self, bars: list[dict], level: float, current_close: float) -> SweepResult:
        for i, bar in enumerate(bars):
            # Wick swept below the level but closed above it
            if bar["l"] < level and bar["c"] > level:
                wick_size = level - bar["l"]
                wick_pct = wick_size / level * 100

                if wick_pct < self.min_wick_pct:
                    continue

                # Check if subsequent bars are holding above the level (reclaim)
                post_bars = bars[i + 1:]
                reclaimed = len(post_bars) > 0 and all(b["c"] > level for b in post_bars)
                current_reclaimed = current_close > level

                return SweepResult(
                    detected=True,
                    swept_level=level,
                    reclaimed=reclaimed or current_reclaimed,
                    sweep_bar_idx=i,
                    wick_size_pct=round(wick_pct, 2),
                    description=f"Swept ${level:.2f} (wick {wick_pct:.1f}%), {'reclaimed' if reclaimed or current_reclaimed else 'NOT reclaimed'}",
                )

        return SweepResult(False, None, False, None, None, f"No sweep at ${level:.2f}")

    def get_vwap_sweep(self, bars: list[dict], vwap: float) -> SweepResult:
        """Specialized check for VWAP sweep and reclaim."""
        return self.detect(bars, [vwap])
