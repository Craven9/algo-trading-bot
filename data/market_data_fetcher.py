"""
data/market_data_fetcher.py — Polygon.io market data interface
Pulls OHLCV bars, level 2 quotes, and news for any ticker.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
import aiohttp

log = logging.getLogger(__name__)

POLYGON_BASE = "https://api.polygon.io"


class MarketDataFetcher:
    def __init__(self, settings: dict):
        self.api_key = settings["data"]["polygon_api_key"]
        self.timeframe = settings["data"]["timeframe"]
        self.timeframe_unit = settings["data"]["timeframe_unit"]
        self.lookback_bars = settings["data"]["lookback_bars"]
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
        return self._session

    async def _get(self, url: str, params: dict = None) -> Optional[dict]:
        try:
            session = await self._get_session()
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json()
                log.warning(f"Polygon API {resp.status} for {url}")
                return None
        except Exception as exc:
            log.error(f"Polygon request failed: {exc}")
            return None

    async def get_ohlcv(self, ticker: str) -> Optional[dict]:
        """
        Fetch OHLCV bars and compute derived fields:
        relative volume, VWAP approximation, and bar metadata.
        Returns a dict with 'bars' list and 'meta' dict.
        """
        end = datetime.now()
        start = end - timedelta(days=5)  # enough history for indicators

        url = (
            f"{POLYGON_BASE}/v2/aggs/ticker/{ticker}/range"
            f"/{self.timeframe}/{self.timeframe_unit}"
            f"/{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}"
        )
        params = {
            "adjusted": "true",
            "sort": "asc",
            "limit": 500,
        }

        data = await self._get(url, params)
        if not data or data.get("resultsCount", 0) == 0:
            return None

        bars = data["results"]

        # Calculate relative volume using the average of prior 20 same-time bars
        avg_volume = sum(b["v"] for b in bars[-20:]) / min(len(bars), 20) if bars else 1
        current_vol = bars[-1]["v"] if bars else 0
        rel_volume = current_vol / avg_volume if avg_volume > 0 else 0

        return {
            "ticker": ticker,
            "bars": bars,          # list of {t, o, h, l, c, v, vw}
            "latest": bars[-1],
            "relative_volume": rel_volume,
            "avg_volume": avg_volume,
            "bar_count": len(bars),
        }

    async def get_level2(self, ticker: str) -> Optional[dict]:
        """Fetch latest NBBO quote (bid/ask spread)."""
        url = f"{POLYGON_BASE}/v2/last/nbbo/{ticker}"
        data = await self._get(url)
        if not data or "results" not in data:
            return None

        result = data["results"]
        bid = result.get("P", 0)
        ask = result.get("p", 0)
        spread = ask - bid
        mid = (bid + ask) / 2 if bid and ask else 0
        spread_pct = (spread / mid * 100) if mid > 0 else 99

        return {
            "bid": bid,
            "ask": ask,
            "spread": spread,
            "spread_pct": spread_pct,
        }

    async def get_snapshot(self, ticker: str) -> Optional[dict]:
        """Get a full market snapshot for a ticker."""
        url = f"{POLYGON_BASE}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"
        data = await self._get(url)
        if not data:
            return None
        return data.get("ticker")

    async def get_market_snapshots(self, tickers: list[str]) -> list[dict]:
        """Batch snapshot request for multiple tickers."""
        ticker_str = ",".join(tickers)
        url = f"{POLYGON_BASE}/v2/snapshot/locale/us/markets/stocks/tickers"
        data = await self._get(url, params={"tickers": ticker_str})
        if not data:
            return []
        return data.get("tickers", [])

    async def get_gainers(self, limit: int = 20) -> list[dict]:
        """Get today's top gainers from Polygon snapshot."""
        url = f"{POLYGON_BASE}/v2/snapshot/locale/us/markets/stocks/gainers"
        data = await self._get(url, params={"include_otc": "false"})
        if not data:
            return []
        return data.get("tickers", [])[:limit]

    async def get_ticker_details(self, ticker: str) -> Optional[dict]:
        """Fetch fundamental details: float, market cap, exchange."""
        url = f"{POLYGON_BASE}/v3/reference/tickers/{ticker}"
        data = await self._get(url)
        if not data:
            return None
        return data.get("results")

    async def get_previous_close(self, ticker: str) -> Optional[float]:
        """Get the prior day's closing price for gap calculation."""
        url = f"{POLYGON_BASE}/v2/aggs/ticker/{ticker}/prev"
        data = await self._get(url)
        if not data or not data.get("results"):
            return None
        return data["results"][0].get("c")

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
