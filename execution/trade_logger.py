"""
execution/trade_logger.py — Structured trade event logging
Writes every order, fill, partial exit, and rejection to JSON log files.
Nothing reads from the database directly except this module.
"""

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    raise TypeError(f"Not serialisable: {type(obj)}")


class TradeLogger:
    def __init__(self, settings: dict):
        self.settings = settings
        log_cfg = settings.get("logging", {})
        self.trade_dir      = Path(log_cfg.get("trade_log_dir",      "logs/trades"))
        self.rejection_dir  = Path(log_cfg.get("rejection_log_dir",  "logs/rejections"))
        self.perf_dir       = Path(log_cfg.get("performance_log_dir","logs/performance"))

        for d in [self.trade_dir, self.rejection_dir, self.perf_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self._open_trades: dict[str, dict] = {}
        self._closed_today: list[dict] = []
        self._today_str = date.today().isoformat()

    # ── Entry ─────────────────────────────────────────────────────────────────

    def log_entry(self, ticker: str, order: dict, verdict, context: dict):
        record = {
            "event": "ENTRY",
            "ticker": ticker,
            "timestamp": datetime.now().isoformat(),
            "order_id": order.get("id"),
            "order_status": order.get("status"),
            "entry_price": order.get("filled_avg_price") or verdict.entry_price,
            "shares": order.get("filled_qty") or verdict.position_size,
            "stop_price": verdict.stop_price,
            "targets": verdict.targets,
            "setup_type": verdict.setup_type,
            "setup_score": verdict.setup_score,
            "probability_pct": round(verdict.probability * 100, 1),
            "risk_reward": verdict.risk_reward,
            "approval_reasons": verdict.approval_reasons,
            "score_breakdown": verdict.score_breakdown,
            "probability_breakdown": verdict.probability_breakdown,
            "news": context.get("news"),
            "market_state": context.get("market_state"),
        }
        self._open_trades[ticker] = record
        self._write(self.trade_dir / f"{ticker}_{self._today_str}.json", record)
        log.info(f"Trade logged: {ticker} ENTRY @ ${record['entry_price']}")

    # ── Exit ──────────────────────────────────────────────────────────────────

    def log_exit(self, position, reason: str, exit_price: Optional[float] = None):
        ticker = position.ticker
        ep = exit_price or position.current_price
        entry_record = self._open_trades.pop(ticker, {})

        pnl = (ep - position.entry_price) * position.remaining_shares
        r_multiple = (ep - position.entry_price) / (position.entry_price - position.initial_stop) \
            if (position.entry_price - position.initial_stop) > 0 else 0

        record = {
            **entry_record,
            "event": "EXIT",
            "exit_timestamp": datetime.now().isoformat(),
            "exit_price": ep,
            "exit_reason": reason,
            "realized_pnl": round(pnl, 2),
            "r_multiple": round(r_multiple, 2),
            "partial_exits": position.partial_exits,
            "breakeven_was_set": position.breakeven_set,
            "duration_minutes": (
                (datetime.now() - position.entry_time).total_seconds() / 60
                if position.entry_time else None
            ),
        }
        self._closed_today.append(record)
        self._write(self.trade_dir / f"{ticker}_{self._today_str}.json", record, append=True)
        log.info(f"Trade logged: {ticker} EXIT @ ${ep:.2f} | PnL ${pnl:.2f} | {r_multiple:.2f}R | {reason}")

    # ── Rejection ─────────────────────────────────────────────────────────────

    def log_rejection(self, ticker: str, verdict):
        if not self.settings.get("logging", {}).get("log_rejections", True):
            return
        record = {
            "event": "REJECTION",
            "ticker": ticker,
            "timestamp": datetime.now().isoformat(),
            "reasons": verdict.rejection_reasons,
            "score_breakdown": verdict.score_breakdown,
            "probability_breakdown": verdict.probability_breakdown,
        }
        rejection_file = self.rejection_dir / f"rejections_{self._today_str}.jsonl"
        with open(rejection_file, "a") as f:
            f.write(json.dumps(record, default=_json_default) + "\n")

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_todays_closed_trades(self) -> list[dict]:
        return list(self._closed_today)

    def get_open_trade_record(self, ticker: str) -> Optional[dict]:
        return self._open_trades.get(ticker)

    def reset_day(self):
        self._closed_today = []
        self._today_str = date.today().isoformat()

    # ── I/O ───────────────────────────────────────────────────────────────────

    def _write(self, path: Path, record: dict, append: bool = False):
        try:
            mode = "a" if append else "w"
            with open(path, mode) as f:
                if append:
                    f.write("\n" + json.dumps(record, indent=2, default=_json_default))
                else:
                    json.dump(record, f, indent=2, default=_json_default)
        except Exception as exc:
            log.exception(f"Failed to write trade log {path}: {exc}")
