"""
risk/risk_manager.py — Position sizing engine
Calculates shares from account risk %, stop distance, and ATR sanity check.
"""

import logging
import math
from typing import Optional

log = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, settings: dict):
        self.settings = settings
        self.risk_cfg = settings["risk"]

    def calculate_shares(
        self,
        account_balance: float,
        entry_price: float,
        stop_price: float,
        atr: Optional[float] = None,
        setup_score: float = 65.0,
    ) -> int:
        """
        Core position sizing formula:
          risk_amount = account_balance × risk_per_trade_%
          stop_distance = entry_price - stop_price
          shares = risk_amount / stop_distance

        ATR sanity: if stop_distance < 0.5 × ATR, the stop is too tight.
        High-quality setups (score >= 80) can use max_risk_per_trade_pct.
        """
        base_risk_pct = self.risk_cfg["risk_per_trade_pct"] / 100
        max_risk_pct  = self.risk_cfg["max_risk_per_trade_pct"] / 100

        # A+ setups can use higher risk allocation
        if setup_score >= 80:
            risk_pct = max_risk_pct
        else:
            risk_pct = base_risk_pct

        # Consecutive loss reduction
        if self.risk_cfg.get("consecutive_loss_size_reduction"):
            # This is wired in by account_risk_guard when needed
            pass

        risk_amount = account_balance * risk_pct
        stop_distance = entry_price - stop_price

        if stop_distance <= 0:
            log.warning(f"Invalid stop distance: entry={entry_price}, stop={stop_price}")
            return 0

        # ATR sanity check — stop too tight?
        if atr and stop_distance < atr * 0.5:
            log.warning(f"Stop distance {stop_distance:.4f} < 0.5×ATR {atr*0.5:.4f} — using ATR-based stop")
            stop_distance = atr * 0.5

        shares = risk_amount / stop_distance
        shares = math.floor(shares)  # always round down

        # Cap: never allocate more than max_exposure_pct of account to one trade
        max_exposure_pct = self.settings["risk"]["max_portfolio_exposure_pct"] / 100
        max_shares_by_exposure = math.floor((account_balance * max_exposure_pct) / entry_price)
        shares = min(shares, max_shares_by_exposure)

        log.debug(
            f"Position size: {shares} shares | "
            f"risk=${risk_amount:.0f} ({risk_pct:.1%}) | "
            f"stop_dist=${stop_distance:.4f} | entry=${entry_price:.2f}"
        )
        return max(shares, 0)

    def apply_streak_reduction(self, shares: int, consecutive_losses: int) -> int:
        """Reduce position size after consecutive losses."""
        threshold = self.risk_cfg.get("consecutive_loss_threshold", 2)
        multiplier = self.risk_cfg.get("consecutive_loss_size_multiplier", 0.5)
        if consecutive_losses >= threshold:
            reduced = math.floor(shares * multiplier)
            log.info(f"Consecutive loss reduction applied: {shares} → {reduced} shares")
            return reduced
        return shares

    def get_risk_amount(self, account_balance: float, shares: int, entry_price: float, stop_price: float) -> float:
        """Calculate actual dollar risk for a given position."""
        return shares * (entry_price - stop_price)

    def get_r_multiple(self, entry: float, exit_price: float, stop: float) -> float:
        """Calculate R multiple for a closed trade."""
        risk = entry - stop
        if risk <= 0:
            return 0
        return (exit_price - entry) / risk
