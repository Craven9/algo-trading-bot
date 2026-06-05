"""
analysis/market_influence_filter.py — Broad market health check
Monitors SPY/QQQ trend, VIX level, and sector context.
"""

import logging
from datetime import datetime
from typing import Optional

from data.market_data_fetcher import MarketDataFetcher
import data.indicator_calculator as ind

log = logging.getLogger(__name__)


class MarketInfluenceFilter:
    def __init__(self, settings: dict, data_fetcher: MarketDataFetcher):
        self.settings = settings
        self.fetcher = data_fetcher
        self.cfg = settings["market_filter"]
        self._cache: Optional[dict] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl_seconds = 120  # refresh every 2 minutes

    async def get_market_state(self) -> dict:
        """Return current broad market state, using cache if fresh."""
        now = datetime.now()
        if (
            self._cache
            and self._cache_time
            and (now - self._cache_time).total_seconds() < self._cache_ttl_seconds
        ):
            return self._cache

        state = await self._fetch_market_state()
        self._cache = state
        self._cache_time = now
        return state

    async def _fetch_market_state(self) -> dict:
        spy_data = await self.fetcher.get_ohlcv(self.cfg.get("spy_ticker", "SPY"))
        qqq_data = await self.fetcher.get_ohlcv(self.cfg.get("qqq_ticker", "QQQ"))

        spy_ok = self._analyze_index(spy_data, "SPY")
        qqq_ok = self._analyze_index(qqq_data, "QQQ")

        # Determine overall bias
        bullish_count = sum(1 for x in [spy_ok, qqq_ok] if x["bias"] == "bullish")
        bearish_count = sum(1 for x in [spy_ok, qqq_ok] if x["bias"] == "bearish")

        if bullish_count >= 2:
            overall_bias = "bullish"
        elif bearish_count >= 2:
            overall_bias = "bearish"
        elif bearish_count == 1 and bullish_count == 0:
            overall_bias = "bearish"
        else:
            overall_bias = "neutral"

        # Block trading if SPY below VWAP and setting enabled
        spy_below_vwap = spy_ok.get("below_vwap", False)
        block_entries = (
            self.cfg.get("pause_if_spy_below_vwap", True) and spy_below_vwap
        )

        return {
            "bias": overall_bias,
            "spy": spy_ok,
            "qqq": qqq_ok,
            "vix": None,  # Polygon free tier doesn't include VIX — extend later
            "block_entries": block_entries,
            "summary": f"Market: {overall_bias.upper()} | SPY {'below' if spy_below_vwap else 'above'} VWAP",
        }

    def _analyze_index(self, data: Optional[dict], symbol: str) -> dict:
        if not data:
            return {"symbol": symbol, "bias": "neutral", "below_vwap": False, "error": True}

        bars = data["bars"]
        indicators = ind.compute_all(bars, self.settings)
        price = indicators.get("latest_close", 0)
        vwap_val = indicators.get("vwap")
        higher_lows = indicators.get("higher_lows", False)
        lower_highs = indicators.get("lower_highs", False)
        rsi_val = indicators.get("rsi", 50)

        below_vwap = vwap_val and price < vwap_val

        if not below_vwap and higher_lows and (rsi_val or 50) > 50:
            bias = "bullish"
        elif below_vwap and lower_highs and (rsi_val or 50) < 50:
            bias = "bearish"
        else:
            bias = "neutral"

        return {
            "symbol": symbol,
            "price": price,
            "vwap": vwap_val,
            "bias": bias,
            "below_vwap": below_vwap,
            "higher_lows": higher_lows,
            "rsi": rsi_val,
        }

    def is_acceptable_for_trading(self, market_state: dict) -> tuple[bool, str]:
        """Returns (allowed, reason)."""
        if market_state.get("block_entries"):
            return False, "SPY below VWAP — entries paused per config"
        if market_state.get("bias") == "bearish":
            return False, "Broad market in bearish state"
        vix = market_state.get("vix")
        max_vix = self.cfg.get("max_acceptable_vix", 35)
        if vix and vix > max_vix:
            return False, f"VIX {vix:.0f} exceeds maximum {max_vix}"
        return True, "Market conditions acceptable"
