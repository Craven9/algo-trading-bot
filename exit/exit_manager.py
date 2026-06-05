"""
exit/exit_manager.py — Orchestrates all exit logic for open positions
Checks every open position on each bar close. Runs through the exit hierarchy in order.
"""

import logging
from datetime import datetime
from typing import Optional

from risk.position_tracker import PositionTracker, Position
from execution.order_executor import OrderExecutor
from execution.trade_logger import TradeLogger
import data.indicator_calculator as ind

log = logging.getLogger(__name__)


class ExitManager:
    def __init__(self, settings: dict, position_tracker: PositionTracker,
                 order_executor: OrderExecutor, trade_logger: TradeLogger):
        self.settings = settings
        self.positions = position_tracker
        self.executor = order_executor
        self.logger = trade_logger
        self.exit_cfg = settings["exits"]

    async def check_position(self, position: Position, ohlcv: dict, market_state: dict):
        """
        Run through all exit checks for a single position.
        Exit hierarchy (in order):
          1. Hard stop hit
          2. Failed breakout / thesis invalidation
          3. VWAP loss (for VWAP setups)
          4. Break-even trigger
          5. First partial profit
          6. Volume fade at resistance
          7. Fibonacci extension targets
          8. Trailing stop update
        """
        bars = ohlcv["bars"]
        if not bars:
            return

        current_bar = bars[-1]
        current_price = current_bar["c"]
        current_low   = current_bar["l"]
        self.positions.update_price(position.ticker, current_price)
        indicators = ind.compute_all(bars, self.settings)

        # ── 1. Hard stop ─────────────────────────────────────────────────────
        if current_low <= position.current_stop:
            await self._exit_full(position, position.current_stop, "Stop loss hit")
            return

        # ── 2. Failed breakout ────────────────────────────────────────────────
        if self.exit_cfg.get("failed_breakout_exit_enabled", True):
            if self._detect_failed_breakout(bars, position):
                await self._exit_full(position, current_price, "Failed breakout — bull trap signal")
                return

        # ── 3. VWAP loss exit ─────────────────────────────────────────────────
        if self.exit_cfg.get("vwap_loss_exit_enabled", True):
            if position.setup_type == "vwap_reclaim":
                vwap = indicators.get("vwap")
                if vwap and current_price < vwap:
                    vol_trend = indicators.get("volume_trend")
                    if vol_trend == "increasing":
                        await self._exit_full(position, current_price, "VWAP lost with increasing volume — thesis invalidated")
                        return

        # ── 4. Break-even trigger ─────────────────────────────────────────────
        if not position.breakeven_set:
            breakeven_r = self.exit_cfg.get("breakeven_at_r", 1.0)
            if position.r_multiple >= breakeven_r:
                self.positions.set_breakeven(position.ticker)

        # ── 5. First partial profit ───────────────────────────────────────────
        if not position.first_partial_taken:
            first_partial_r = self.exit_cfg.get("first_partial_at_r", 1.5)
            if position.r_multiple >= first_partial_r and position.remaining_shares > 1:
                pct = self.exit_cfg.get("first_partial_size_pct", 40) / 100
                shares_to_sell = max(1, int(position.remaining_shares * pct))
                await self._exit_partial(position, shares_to_sell, current_price, f"First target {first_partial_r}R hit")
                position.first_partial_taken = True

        # ── 6. Second partial profit ──────────────────────────────────────────
        elif not position.second_partial_taken and position.remaining_shares > 1:
            second_partial_r = self.exit_cfg.get("second_partial_at_r", 2.5)
            if position.r_multiple >= second_partial_r:
                pct = self.exit_cfg.get("second_partial_size_pct", 25) / 100
                shares_to_sell = max(1, int(position.remaining_shares * pct))
                await self._exit_partial(position, shares_to_sell, current_price, f"Second target {second_partial_r}R hit")
                position.second_partial_taken = True

        # ── 7. Volume fade exit (runner management) ───────────────────────────
        if self.exit_cfg.get("volume_fade_exit_enabled", True) and position.first_partial_taken:
            if self._detect_volume_fade(bars, indicators):
                position.exit_warnings.append("Volume fading at resistance")
                log.info(f"{position.ticker}: Volume fade warning added")

        # ── 8. Fibonacci extension target exits ───────────────────────────────
        if position.targets and position.first_partial_taken:
            for target in sorted(position.targets):
                if current_price >= target and position.remaining_shares > 1:
                    shares_to_sell = max(1, int(position.remaining_shares * 0.25))
                    await self._exit_partial(position, shares_to_sell, current_price, f"Fibonacci extension target ${target:.2f} hit")
                    break

        # ── 9. Trailing stop update ───────────────────────────────────────────
        if position.first_partial_taken:
            new_stop = self._calc_trailing_stop(bars, position, indicators)
            if new_stop and new_stop > position.current_stop:
                self.positions.update_stop(position.ticker, new_stop)

        # ── 10. Time-based reassessment ───────────────────────────────────────
        if self._is_time_exit(position):
            if not position.breakeven_set:
                log.info(f"{position.ticker}: Time limit reached without reaching breakeven — manual review flagged")
                position.exit_warnings.append("Time limit reached without reaching breakeven")

    # ── Exit helpers ──────────────────────────────────────────────────────────

    async def _exit_full(self, position: Position, exit_price: float, reason: str):
        log.info(f"FULL EXIT: {position.ticker} @ ${exit_price:.2f} | {reason}")
        await self.executor.close_position(position.ticker, reason=reason)
        self.logger.log_exit(position, reason=reason, exit_price=exit_price)
        self.positions.remove_position(position.ticker)

    async def _exit_partial(self, position: Position, shares: int, exit_price: float, reason: str):
        log.info(f"PARTIAL EXIT: {position.ticker} {shares} shares @ ${exit_price:.2f} | {reason}")
        await self.executor.close_partial(position.ticker, shares=shares, reason=reason)
        self.positions.record_partial_exit(position.ticker, shares, exit_price, reason)

    def _detect_failed_breakout(self, bars: list[dict], position: Position) -> bool:
        """
        Bull trap: price broke to a new high but closed back below the prior high
        within 1–2 bars with above-average volume on the down move.
        """
        if len(bars) < 4:
            return False
        last = bars[-1]
        prev = bars[-2]
        # Price made new high then closed below prior high with big down volume
        if last["h"] > prev["h"] and last["c"] < prev["h"]:
            # Volume on the reversal bar should be above average
            avg_vol = sum(b["v"] for b in bars[-10:-1]) / 9 if len(bars) >= 10 else last["v"]
            if last["v"] > avg_vol * 1.2:
                return True
        return False

    def _detect_volume_fade(self, bars: list[dict], indicators: dict) -> bool:
        """Volume drops to <50% of prior bar while price stalls at resistance."""
        if len(bars) < 3:
            return False
        threshold = self.exit_cfg.get("volume_fade_threshold_pct", 50) / 100
        current_vol = bars[-1]["v"]
        prior_vol   = bars[-2]["v"]
        price_stalling = abs(bars[-1]["c"] - bars[-2]["c"]) / bars[-2]["c"] < 0.003
        return current_vol < prior_vol * threshold and price_stalling

    def _calc_trailing_stop(self, bars: list[dict], position: Position, indicators: dict) -> Optional[float]:
        """Trail the stop under the most recent higher low (5-min chart)."""
        swing_lows = indicators.get("swing_lows", [])
        if not swing_lows:
            return None
        # Use the highest swing low that is below the current price
        price = position.current_price
        valid_lows = [sl for sl in swing_lows if sl < price and sl > position.entry_price]
        if not valid_lows:
            return None
        return max(valid_lows) * 0.998  # small buffer below the swing low

    def _is_time_exit(self, position: Position) -> bool:
        max_hours = self.exit_cfg.get("time_based_reassess_hours", 2)
        if not position.entry_time:
            return False
        elapsed = (datetime.now() - position.entry_time).total_seconds() / 3600
        return elapsed >= max_hours
