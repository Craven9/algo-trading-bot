"""
risk/position_tracker.py — Tracks all open positions and their lifecycle
Maintains cost basis, current P&L, stop levels, and partial exit history.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class Position:
    ticker: str
    entry_price: float
    shares: int
    stop_price: float
    initial_stop: float
    targets: list[float]
    setup_type: str
    setup_score: float
    entry_time: datetime
    order_id: str

    # Mutable state
    current_price: float = 0.0
    remaining_shares: int = 0
    breakeven_set: bool = False
    first_partial_taken: bool = False
    second_partial_taken: bool = False
    trailing_stop: Optional[float] = None
    exit_warnings: list[str] = field(default_factory=list)
    partial_exits: list[dict] = field(default_factory=list)

    def __post_init__(self):
        self.remaining_shares = self.shares
        self.current_price = self.entry_price

    @property
    def unrealized_pnl(self) -> float:
        return (self.current_price - self.entry_price) * self.remaining_shares

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.entry_price == 0:
            return 0
        return (self.current_price - self.entry_price) / self.entry_price * 100

    @property
    def r_multiple(self) -> float:
        risk = self.entry_price - self.initial_stop
        if risk <= 0:
            return 0
        return (self.current_price - self.entry_price) / risk

    @property
    def current_stop(self) -> float:
        return self.trailing_stop or self.stop_price

    @property
    def is_above_breakeven(self) -> bool:
        return self.current_price > self.entry_price

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "shares": self.shares,
            "remaining_shares": self.remaining_shares,
            "stop_price": self.current_stop,
            "initial_stop": self.initial_stop,
            "targets": self.targets,
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "unrealized_pnl_pct": round(self.unrealized_pnl_pct, 2),
            "r_multiple": round(self.r_multiple, 2),
            "setup_type": self.setup_type,
            "setup_score": self.setup_score,
            "entry_time": self.entry_time.isoformat(),
            "breakeven_set": self.breakeven_set,
            "first_partial_taken": self.first_partial_taken,
            "exit_warnings": self.exit_warnings,
        }


class PositionTracker:
    def __init__(self, settings: dict):
        self.settings = settings
        self._positions: dict[str, Position] = {}

    def add_position(self, ticker: str, order: dict, verdict) -> Position:
        pos = Position(
            ticker=ticker,
            entry_price=order.get("filled_avg_price", verdict.entry_price),
            shares=order.get("filled_qty", verdict.position_size),
            stop_price=verdict.stop_price,
            initial_stop=verdict.stop_price,
            targets=verdict.targets,
            setup_type=verdict.setup_type,
            setup_score=verdict.setup_score,
            entry_time=datetime.now(),
            order_id=order.get("id", ""),
        )
        self._positions[ticker] = pos
        log.info(f"Position added: {ticker} | {pos.shares} shares @ ${pos.entry_price:.2f} | stop=${pos.stop_price:.2f}")
        return pos

    def update_price(self, ticker: str, price: float):
        if ticker in self._positions:
            self._positions[ticker].current_price = price

    def update_stop(self, ticker: str, new_stop: float):
        pos = self._positions.get(ticker)
        if pos and new_stop > pos.current_stop:  # stops only move up
            old = pos.current_stop
            pos.trailing_stop = new_stop
            log.info(f"Stop raised for {ticker}: ${old:.2f} → ${new_stop:.2f}")

    def set_breakeven(self, ticker: str):
        pos = self._positions.get(ticker)
        if pos and not pos.breakeven_set:
            pos.trailing_stop = pos.entry_price
            pos.breakeven_set = True
            log.info(f"Breakeven stop set for {ticker} @ ${pos.entry_price:.2f}")

    def record_partial_exit(self, ticker: str, shares_exited: int, exit_price: float, reason: str):
        pos = self._positions.get(ticker)
        if pos:
            pos.remaining_shares -= shares_exited
            pnl = (exit_price - pos.entry_price) * shares_exited
            pos.partial_exits.append({
                "shares": shares_exited,
                "price": exit_price,
                "pnl": round(pnl, 2),
                "reason": reason,
                "time": datetime.now().isoformat(),
            })
            log.info(f"Partial exit {ticker}: {shares_exited} shares @ ${exit_price:.2f} | PnL ${pnl:.2f} | {reason}")

    def remove_position(self, ticker: str) -> Optional[Position]:
        return self._positions.pop(ticker, None)

    def get_open_positions(self) -> list[Position]:
        return list(self._positions.values())

    def get_position(self, ticker: str) -> Optional[Position]:
        return self._positions.get(ticker)

    def has_open_positions(self) -> bool:
        return bool(self._positions)

    def get_daily_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self._positions.values())
