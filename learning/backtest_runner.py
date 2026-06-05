"""
learning/backtest_runner.py — Runs a setup against historical bar data
Used to validate a setup after underperformance or market regime change.
Requires Polygon.io historical data access.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger(__name__)


class BacktestRunner:
    def __init__(self, settings: dict, data_fetcher=None, quality_gate=None):
        self.settings = settings
        self.fetcher = data_fetcher
        self.gate = quality_gate

    async def run(self, setup_type: str, tickers: list[str], days: int = 30) -> dict:
        """
        Replay the quality gate over historical data for a set of tickers.
        Returns simulated trade results for the given setup type.

        Note: This is a simplified backtest — it does not account for
        slippage, partial fills, or intraday execution dynamics.
        """
        log.info(f"Backtest: {setup_type} | {len(tickers)} tickers | {days} days")

        results = []
        end = datetime.now()
        start = end - timedelta(days=days)

        for ticker in tickers:
            try:
                result = await self._backtest_ticker(ticker, setup_type, start, end)
                if result:
                    results.append(result)
            except Exception as exc:
                log.warning(f"Backtest error for {ticker}: {exc}")

        if not results:
            return {"message": "No backtest results", "setup_type": setup_type}

        wins   = [r for r in results if r.get("r_multiple", 0) > 0]
        losses = [r for r in results if r.get("r_multiple", 0) <= 0]
        total  = len(results)

        return {
            "setup_type": setup_type,
            "period_days": days,
            "total_trades": total,
            "win_rate": round(len(wins) / total, 3) if total else 0,
            "avg_r": round(sum(r.get("r_multiple", 0) for r in results) / total, 3) if total else 0,
            "max_r":  max((r.get("r_multiple", 0) for r in results), default=0),
            "min_r":  min((r.get("r_multiple", 0) for r in results), default=0),
            "results": results,
        }

    async def _backtest_ticker(self, ticker: str, setup_type: str, start: datetime, end: datetime) -> Optional[dict]:
        """Placeholder — implement full bar-by-bar replay here."""
        log.debug(f"Backtesting {ticker} for {setup_type}")
        # TODO: implement bar-by-bar replay using historical OHLCV from Polygon
        return None
