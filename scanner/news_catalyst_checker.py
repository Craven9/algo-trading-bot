"""
scanner/news_catalyst_checker.py — Checks for confirmed news catalysts
Uses Polygon.io news API to find and score catalyst quality.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from data.market_data_fetcher import MarketDataFetcher

log = logging.getLogger(__name__)

# Keywords that indicate a strong, confirmed catalyst
STRONG_CATALYST_KEYWORDS = [
    "fda approval", "fda approved", "clinical trial", "phase 3", "phase 2",
    "earnings beat", "revenue beat", "guidance raise", "acquisition", "merger",
    "contract awarded", "partnership", "buyout", "takeover", "going private",
    "reverse split", "stock split", "buyback", "dividend",
]

WEAK_CATALYST_KEYWORDS = [
    "analyst upgrade", "price target", "initiated coverage",
    "sector rotation", "market rally", "meme", "reddit", "social media",
]

NEGATIVE_KEYWORDS = [
    "fda rejection", "clinical trial failed", "earnings miss", "guidance cut",
    "lawsuit", "investigation", "sec subpoena", "bankruptcy",
]


class NewsCatalystChecker:
    def __init__(self, settings: dict):
        self.settings = settings
        self.fetcher = MarketDataFetcher(settings)

    async def get_catalyst(self, ticker: str) -> dict:
        """
        Fetch and score news catalyst for a ticker.
        Returns a dict with catalyst score (0-4) and details.
        """
        url = f"https://api.polygon.io/v2/reference/news"
        params = {
            "ticker": ticker,
            "published_utc.gte": (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "order": "desc",
            "limit": 10,
        }

        data = await self.fetcher._get(url, params)
        if not data or not data.get("results"):
            return {"score": 0, "has_catalyst": False, "headline": None, "type": "none"}

        articles = data["results"]
        best_score = 0
        best_headline = None
        catalyst_type = "none"

        for article in articles:
            title = (article.get("title") or "").lower()
            description = (article.get("description") or "").lower()
            text = title + " " + description

            # Check for negative news first — flag it
            if any(kw in text for kw in NEGATIVE_KEYWORDS):
                return {
                    "score": 0,
                    "has_catalyst": False,
                    "headline": article.get("title"),
                    "type": "negative",
                    "warning": "Negative news detected",
                }

            # Score positive catalyst
            if any(kw in text for kw in STRONG_CATALYST_KEYWORDS):
                score = 4
                cat_type = "strong"
            elif any(kw in text for kw in WEAK_CATALYST_KEYWORDS):
                score = 2
                cat_type = "weak"
            else:
                score = 1
                cat_type = "unknown"

            if score > best_score:
                best_score = score
                best_headline = article.get("title")
                catalyst_type = cat_type

        return {
            "score": best_score,
            "has_catalyst": best_score >= 3,
            "headline": best_headline,
            "type": catalyst_type,
        }
