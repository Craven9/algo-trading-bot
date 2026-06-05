"""
analysis/opening_range_analyzer.py — Opening range high/low tracker
Defines the ORH and ORL, monitors breakouts and failures.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, time as dt_time
from typing import Optional
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")


@dataclass
class OpeningRange:
    high: float
    low: float
    range_pct: float
    formed: bool


class OpeningRangeAnalyzer:
    def __init__(self, settings: dict):
        self.settings = settings
        self.or_minutes = settings["indicators"].get("opening_range_minutes", 15)

    def get_opening_range(self, bars: list[dict]) -> Optional[OpeningRange]:
        """
        Calculate ORH/ORL from the first N minutes of the session.
        Bars are expected to be 5-minute bars with Unix ms timestamps.
        """
        if not bars:
            return None

        market_open_ms = self._market_open_ms(bars[0]["t"])
        cutoff_ms = market_open_ms + (self.or_minutes * 60 * 1000)

        or_bars = [b for b in bars if market_open_ms <= b["t"] < cutoff_ms]
        if len(or_bars) < 1:
            return None

        orh = max(b["h"] for b in or_bars)
        orl = min(b["l"] for b in or_bars)
        range_pct = (orh - orl) / orl * 100 if orl > 0 else 0

        return OpeningRange(high=orh, low=orl, range_pct=range_pct, formed=True)

    def get_or_status(self, bars: list[dict], current_price: float) -> str:
        """
        Returns one of:
          'above_orh_holding', 'approaching_orh', 'inside_range',
          'approaching_orl', 'below_orl', 'or_not_formed'
        """
        or_range = self.get_opening_range(bars)
        if not or_range or not or_range.formed:
            return "or_not_formed"

        orh = or_range.high
        orl = or_range.low
        threshold = (orh - orl) * 0.1  # 10% of range as "approaching"

        if current_price > orh:
            # Check if it's holding above (last 2+ bars above ORH)
            recent_closes = [b["c"] for b in bars[-3:]]
            if all(c > orh for c in recent_closes):
                return "above_orh_holding"
            return "above_orh"
        elif current_price > orh - threshold:
            return "approaching_orh"
        elif current_price < orl:
            return "below_orl"
        elif current_price < orl + threshold:
            return "approaching_orl"
        else:
            return "inside_range"

    def _market_open_ms(self, first_bar_ts: int) -> int:
        """Snap to 9:30 AM ET on the same day as first_bar_ts."""
        dt = datetime.fromtimestamp(first_bar_ts / 1000, tz=ET)
        open_dt = dt.replace(hour=9, minute=30, second=0, microsecond=0)
        return int(open_dt.timestamp() * 1000)
