"""
risk/account_risk_guard.py — Account-level risk enforcement
Enforces daily loss limit, max open positions, max exposure, and loss streaks.
"""

import logging
from datetime import date
from typing import Optional

log = logging.getLogger(__name__)


class AccountRiskGuard:
    def __init__(self, settings: dict, position_tracker=None):
        self.settings = settings
        self.position_tracker = position_tracker
        self.risk_cfg = settings["risk"]

        # Intraday state (resets at market open)
        self._trading_date: Optional[date] = None
        self._daily_realized_pnl: float = 0.0
        self._trades_today: int = 0
        self._consecutive_losses: int = 0
        self._account_equity: float = 100_000.0  # updated by broker sync

    # ── State sync ────────────────────────────────────────────────────────────

    def sync_equity(self, equity: float):
        self._account_equity = equity

    def record_closed_trade(self, pnl: float):
        """Called by trade_logger after every exit."""
        self._daily_realized_pnl += pnl
        self._trades_today += 1
        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

    def reset_day(self):
        """Called at market open each day."""
        self._trading_date = date.today()
        self._daily_realized_pnl = 0.0
        self._trades_today = 0
        self._consecutive_losses = 0
        log.info(f"Account risk guard reset for {self._trading_date}")

    # ── Guards ────────────────────────────────────────────────────────────────

    def can_open_new_position(self) -> bool:
        state = self.get_state()
        return not (
            state["daily_loss_limit_hit"]
            or state["max_positions_hit"]
            or state["max_exposure_hit"]
        )

    def get_state(self) -> dict:
        open_positions = self.position_tracker.get_open_positions() if self.position_tracker else []
        open_count = len(open_positions)
        max_positions = self.risk_cfg["max_open_positions"]

        # Total current exposure
        total_exposure = sum(
            p.current_price * p.shares for p in open_positions
        ) if open_positions else 0
        exposure_pct = (total_exposure / self._account_equity * 100) if self._account_equity > 0 else 0
        max_exposure = self.risk_cfg["max_portfolio_exposure_pct"]

        # Daily loss limit
        daily_loss_pct = abs(min(self._daily_realized_pnl, 0)) / self._account_equity * 100 if self._account_equity > 0 else 0
        daily_loss_limit = self.risk_cfg["daily_loss_limit_pct"]
        daily_limit_hit = daily_loss_pct >= daily_loss_limit

        # Unrealized P&L
        unrealized_pnl = sum(
            (p.current_price - p.entry_price) * p.shares for p in open_positions
        ) if open_positions else 0

        return {
            "equity": self._account_equity,
            "daily_realized_pnl": round(self._daily_realized_pnl, 2),
            "daily_unrealized_pnl": round(unrealized_pnl, 2),
            "daily_total_pnl": round(self._daily_realized_pnl + unrealized_pnl, 2),
            "daily_loss_pct": round(daily_loss_pct, 2),
            "daily_loss_limit": daily_loss_limit,
            "daily_loss_limit_hit": daily_limit_hit,
            "daily_loss_limit_used_pct": round(daily_loss_pct / daily_loss_limit * 100, 1) if daily_loss_limit else 0,
            "open_positions": open_count,
            "max_positions": max_positions,
            "max_positions_hit": open_count >= max_positions,
            "exposure_pct": round(exposure_pct, 2),
            "max_exposure_pct": max_exposure,
            "max_exposure_hit": exposure_pct >= max_exposure,
            "consecutive_losses": self._consecutive_losses,
            "trades_today": self._trades_today,
        }

    def get_consecutive_losses(self) -> int:
        return self._consecutive_losses
