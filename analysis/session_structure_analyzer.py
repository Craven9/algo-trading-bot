"""
analysis/session_structure_analyzer.py — Reads intraday trend structure
Identifies higher lows, lower highs, trend breaks, and consolidation zones.
"""

import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class StructureResult:
    trend: str                    # "uptrend", "downtrend", "sideways"
    higher_lows: bool
    lower_highs: bool
    consolidating: bool
    last_swing_high: Optional[float]
    last_swing_low: Optional[float]
    support_levels: list[float]
    resistance_levels: list[float]
    trend_break_up: bool          # recent break of downtrend structure
    trend_break_down: bool        # recent break of uptrend structure
    description: str


class SessionStructureAnalyzer:
    def __init__(self, settings: dict):
        self.settings = settings
        self.swing_lookback = 3   # bars each side to confirm a swing point

    def analyze(self, bars: list[dict]) -> StructureResult:
        if len(bars) < 20:
            return StructureResult(
                trend="unknown", higher_lows=False, lower_highs=False,
                consolidating=False, last_swing_high=None, last_swing_low=None,
                support_levels=[], resistance_levels=[],
                trend_break_up=False, trend_break_down=False,
                description="Insufficient data"
            )

        swing_highs = self._find_swings(bars, "high")
        swing_lows  = self._find_swings(bars, "low")

        higher_lows  = self._is_higher_lows(swing_lows)
        lower_highs  = self._is_lower_highs(swing_highs)
        higher_highs = self._is_higher_highs(swing_highs)
        lower_lows   = self._is_lower_lows(swing_lows)

        # Determine trend
        if higher_lows and higher_highs:
            trend = "uptrend"
        elif lower_highs and lower_lows:
            trend = "downtrend"
        else:
            trend = "sideways"

        # Detect consolidation: narrow range in the last 6 bars
        recent = bars[-6:]
        recent_range_pct = (
            (max(b["h"] for b in recent) - min(b["l"] for b in recent))
            / bars[-1]["c"] * 100
        ) if recent else 0
        consolidating = recent_range_pct < 1.5

        # Trend breaks: structure shift in most recent swing
        trend_break_up = lower_highs and swing_highs and swing_highs[-1] > (swing_highs[-2] if len(swing_highs) >= 2 else 0)
        trend_break_down = higher_lows and swing_lows and swing_lows[-1] < (swing_lows[-2] if len(swing_lows) >= 2 else float("inf"))

        # Support / resistance = last 3 swing lows / highs
        support_levels    = sorted(set(round(l, 2) for l in swing_lows[-3:]))
        resistance_levels = sorted(set(round(h, 2) for h in swing_highs[-3:]))

        desc_parts = [trend.upper()]
        if higher_lows:    desc_parts.append("higher lows")
        if higher_highs:   desc_parts.append("higher highs")
        if lower_highs:    desc_parts.append("lower highs")
        if lower_lows:     desc_parts.append("lower lows")
        if consolidating:  desc_parts.append("consolidating")
        if trend_break_up: desc_parts.append("⚡ trend break UP")

        return StructureResult(
            trend=trend,
            higher_lows=higher_lows,
            lower_highs=lower_highs,
            consolidating=consolidating,
            last_swing_high=swing_highs[-1] if swing_highs else None,
            last_swing_low=swing_lows[-1]  if swing_lows  else None,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            trend_break_up=trend_break_up,
            trend_break_down=trend_break_down,
            description=" | ".join(desc_parts),
        )

    def _find_swings(self, bars: list[dict], side: str) -> list[float]:
        n = self.swing_lookback
        field_hi = "h"
        field_lo = "l"
        result = []
        for i in range(n, len(bars) - n):
            if side == "high":
                val = bars[i][field_hi]
                if all(bars[j][field_hi] < val for j in range(i - n, i + n + 1) if j != i):
                    result.append(val)
            else:
                val = bars[i][field_lo]
                if all(bars[j][field_lo] > val for j in range(i - n, i + n + 1) if j != i):
                    result.append(val)
        return result

    def _is_higher_lows(self, lows: list[float], count: int = 2) -> bool:
        if len(lows) < count + 1:
            return False
        recent = lows[-(count + 1):]
        return all(recent[i] > recent[i - 1] for i in range(1, len(recent)))

    def _is_lower_highs(self, highs: list[float], count: int = 2) -> bool:
        if len(highs) < count + 1:
            return False
        recent = highs[-(count + 1):]
        return all(recent[i] < recent[i - 1] for i in range(1, len(recent)))

    def _is_higher_highs(self, highs: list[float], count: int = 2) -> bool:
        if len(highs) < count + 1:
            return False
        recent = highs[-(count + 1):]
        return all(recent[i] > recent[i - 1] for i in range(1, len(recent)))

    def _is_lower_lows(self, lows: list[float], count: int = 2) -> bool:
        if len(lows) < count + 1:
            return False
        recent = lows[-(count + 1):]
        return all(recent[i] < recent[i - 1] for i in range(1, len(recent)))
