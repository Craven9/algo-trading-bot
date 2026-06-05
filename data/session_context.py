"""
data/session_context.py — Market session state management
Tracks pre-market, opening, active, lunch, EOD, and after-hours sessions.
"""

import logging
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

SESSIONS = {
    "PRE_MARKET":  (dt_time(4, 0),   dt_time(9, 30)),
    "OPENING":     (dt_time(9, 30),  dt_time(10, 0)),
    "ACTIVE":      (dt_time(10, 0),  dt_time(15, 45)),
    "EOD":         (dt_time(15, 45), dt_time(16, 0)),
    "AFTER_HOURS": (dt_time(16, 0),  dt_time(20, 0)),
    "CLOSED":      (dt_time(20, 0),  dt_time(4, 0)),
}


class SessionContext:
    def __init__(self, settings: dict):
        self.settings = settings
        self._block_first_minutes = settings["entry"].get("block_first_minutes", 15)
        self._eod_minutes = settings["exits"].get("eod_exit_minutes_before_close", 15)
        self._lunch_enabled = settings["entry"].get("block_lunch_window", False)
        self._lunch_start = settings["entry"].get("lunch_window_start", "12:00")
        self._lunch_end = settings["entry"].get("lunch_window_end", "13:00")

    def get_session(self, now: datetime = None) -> str:
        """Return the current session name."""
        if now is None:
            now = datetime.now()
        now_et = now.astimezone(ET)
        t = now_et.time()

        market_open = dt_time(9, 30)
        market_close = dt_time(16, 0)
        eod_start = dt_time(15, 60 - self._eod_minutes)
        opening_end = dt_time(9, 30 + self._block_first_minutes)

        if t < dt_time(4, 0) or t >= dt_time(20, 0):
            return "CLOSED"
        if t < market_open:
            return "PRE_MARKET"
        if t < opening_end:
            return "OPENING"  # blocked from entries
        if t >= eod_start and t < market_close:
            return "EOD"
        if t >= market_close:
            return "AFTER_HOURS"

        # Lunch window check
        if self._lunch_enabled:
            ls = dt_time(*map(int, self._lunch_start.split(":")))
            le = dt_time(*map(int, self._lunch_end.split(":")))
            if ls <= t < le:
                return "LUNCH"

        return "ACTIVE"

    def is_market_open(self, now: datetime = None) -> bool:
        return self.get_session(now) in ("OPENING", "ACTIVE", "LUNCH")

    def is_entry_allowed(self, now: datetime = None) -> bool:
        return self.get_session(now) == "ACTIVE"

    def minutes_until_close(self, now: datetime = None) -> float:
        if now is None:
            now = datetime.now()
        now_et = now.astimezone(ET)
        close_et = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        delta = (close_et - now_et).total_seconds() / 60
        return max(delta, 0)
