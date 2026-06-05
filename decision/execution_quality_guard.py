"""
decision/execution_quality_guard.py — Pre-execution sanity check
Verifies spread, liquidity, and timing are acceptable right before order placement.
This runs AFTER the quality gate approval, as a final safety net.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")


class ExecutionQualityGuard:
    def __init__(self, settings: dict):
        self.settings = settings
        self.exec_cfg = settings["execution"]
        self.entry_cfg = settings["entry"]

    def check(self, ticker: str, entry_price: float, level2: dict, timestamp: datetime) -> tuple[bool, str]:
        """
        Returns (ok, reason).
        Called immediately before placing an order.
        """
        now_et = timestamp.astimezone(ET) if timestamp.tzinfo else datetime.now(ET)
        t = now_et.time()

        # Timing: no trades within 2 minutes of market open
        from datetime import time as dt_time
        open_cutoff = dt_time(9, 32)
        close_cutoff = dt_time(15, 50)

        if t < open_cutoff:
            return False, "Too close to market open (within 2 minutes)"
        if t > close_cutoff:
            return False, "Too close to market close (within 10 minutes)"

        # Spread check (real-time — may have changed since quality gate ran)
        if level2:
            spread_pct = level2.get("spread_pct", 0)
            max_spread = self.exec_cfg["max_spread_pct"]
            if spread_pct > max_spread:
                return False, f"Spread {spread_pct:.2f}% exceeds max {max_spread}% at execution time"

            # Liquidity check
            bid = level2.get("bid", 0)
            ask = level2.get("ask", 0)
            if bid == 0 or ask == 0:
                return False, "No valid bid/ask — cannot determine execution quality"

        # Price sanity: entry price within 1% of last quote
        if level2 and entry_price:
            mid = (level2.get("bid", entry_price) + level2.get("ask", entry_price)) / 2
            slippage_pct = abs(entry_price - mid) / mid * 100 if mid > 0 else 0
            if slippage_pct > 1.0:
                return False, f"Entry price ${entry_price:.2f} is {slippage_pct:.1f}% from current mid ${mid:.2f}"

        return True, "Execution conditions acceptable"
