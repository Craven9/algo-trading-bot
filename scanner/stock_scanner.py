"""
scanner/stock_scanner.py — Screens for momentum candidates
Uses Polygon.io gainers, relative volume, price, and float criteria.
Fast cheap checks first; expensive analysis only on survivors.
"""

import asyncio
import logging
from typing import Optional

from data.market_data_fetcher import MarketDataFetcher

log = logging.getLogger(__name__)


class StockScanner:
    def __init__(self, settings: dict, data_fetcher: MarketDataFetcher):
        self.settings = settings
        self.fetcher = data_fetcher
        self.cfg = settings["scanner"]
        self._watchlist: list[str] = self._load_watchlist()

    def _load_watchlist(self) -> list[str]:
        import json
        from pathlib import Path
        p = Path("watchlist/manual_watchlist.json")
        if p.exists():
            data = json.loads(p.read_text())
            return data.get("tickers", [])
        return []

    async def get_candidates(self) -> list[str]:
        """
        Return a list of ticker symbols that passed the fast screen.
        Sources: Polygon gainers + manual watchlist.
        """
        if not self.cfg.get("enabled", True):
            return []

        # Gather candidates from both sources concurrently
        gainers_task = self.fetcher.get_gainers(limit=30)
        results = await asyncio.gather(gainers_task, return_exceptions=True)

        gainer_tickers = []
        if not isinstance(results[0], Exception):
            for snap in results[0]:
                ticker = snap.get("ticker", "")
                day = snap.get("day", {})
                prev_day = snap.get("prevDay", {})

                # Quick scalar checks before any further API calls
                if self._passes_fast_screen(ticker, snap, day, prev_day):
                    gainer_tickers.append(ticker)

        # Merge with watchlist (deduped)
        all_candidates = list(dict.fromkeys(self._watchlist + gainer_tickers))
        max_candidates = self.cfg.get("max_candidates_per_cycle", 20)
        candidates = all_candidates[:max_candidates]

        log.info(f"Scanner: {len(candidates)} candidates ({len(gainer_tickers)} gainers, {len(self._watchlist)} watchlist)")
        return candidates

    def _passes_fast_screen(self, ticker: str, snap: dict, day: dict, prev_day: dict) -> bool:
        """Fast scalar checks — no API calls."""
        min_price = self.cfg.get("min_price", 5.0)
        max_price = self.cfg.get("max_price", 500.0)
        min_rv = self.cfg.get("min_relative_volume", 2.0)

        price = day.get("c", 0) or day.get("o", 0)
        if not (min_price <= price <= max_price):
            return False

        # Relative volume (today vs prior close volume)
        today_vol = day.get("v", 0)
        prev_vol = prev_day.get("v", 1)
        rv = today_vol / prev_vol if prev_vol else 0
        if rv < min_rv:
            return False

        # Skip OTC and if ticker looks like preferred equity or warrants
        if any(c in ticker for c in [".", "+", "W", "R"]) and len(ticker) > 4:
            return False

        return True

    async def get_float(self, ticker: str) -> Optional[float]:
        """Fetch share float from Polygon reference data (millions)."""
        details = await self.fetcher.get_ticker_details(ticker)
        if not details:
            return None
        shares_outstanding = details.get("share_class_shares_outstanding", 0)
        if shares_outstanding:
            return shares_outstanding / 1_000_000
        return None

    async def passes_float_check(self, ticker: str) -> bool:
        max_float = self.cfg.get("max_float_millions", 50)
        float_val = await self.get_float(ticker)
        if float_val is None:
            return True  # Don't block if we can't fetch float
        return float_val <= max_float

    def reload_watchlist(self):
        self._watchlist = self._load_watchlist()
        log.info(f"Watchlist reloaded: {len(self._watchlist)} tickers")
