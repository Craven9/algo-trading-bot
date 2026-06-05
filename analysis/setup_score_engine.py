"""
analysis/setup_score_engine.py — Produces 0–100 setup quality score
Assembles all technical factor scores using configurable weights.
The score engine applies weights; setup detectors identify patterns.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class ScoreFactor:
    name: str
    score: float
    max_score: float
    reason: str


@dataclass
class SetupScoreResult:
    total_score: float
    max_possible: float
    normalized: float          # 0–100
    factors: list[ScoreFactor] = field(default_factory=list)
    hard_blocked: bool = False
    block_reasons: list[str] = field(default_factory=list)
    setup_type: str = "unknown"

    @property
    def passed(self) -> bool:
        return not self.hard_blocked and self.normalized >= 65

    def to_dict(self) -> dict:
        return {
            "score": round(self.normalized, 1),
            "setup_type": self.setup_type,
            "passed": self.passed,
            "hard_blocked": self.hard_blocked,
            "block_reasons": self.block_reasons,
            "factors": [
                {"name": f.name, "score": f.score, "max": f.max_score, "reason": f.reason}
                for f in self.factors
            ],
        }


class SetupScoreEngine:
    """
    Scores the technical quality of a setup on a 0–100 scale.
    Weights are loaded from strategy_profiles.json for the active setup type,
    falling back to defaults if the setup type is unknown.
    """

    DEFAULT_WEIGHTS = {
        "vwap_position": 15,
        "key_level_behavior": 15,
        "volume_confirmation": 15,
        "market_structure": 10,
        "rsi_momentum": 10,
        "macd_signal": 8,
        "fibonacci_proximity": 8,
        "opening_range_status": 8,
        "liquidity_sweep": 7,
        "catalyst": 4,
    }

    def __init__(self, settings: dict, strategy_profiles: dict = None):
        self.settings = settings
        self.profiles = strategy_profiles or {}
        self.min_score = settings["entry"]["min_setup_score"]

    def score(self, context: dict, setup_type: str = "unknown") -> SetupScoreResult:
        """
        Score the setup in context.
        context must contain: indicators, ohlcv, news, setup_signal
        """
        indicators = context.get("indicators", {})
        ohlcv = context.get("ohlcv", {})
        news = context.get("news", {})
        setup_signal = context.get("setup_signal", {})
        latest = indicators.get("latest_bar", {})
        price = indicators.get("latest_close", 0)

        weights = self._get_weights(setup_type)
        factors = []
        block_reasons = []

        # ── 1. VWAP position and reclaim quality ─────────────────────────────
        vwap = indicators.get("vwap")
        vwap_pos = indicators.get("price_vs_vwap", "below")
        vwap_score = 0
        if vwap:
            if vwap_pos == "above":
                vwap_score = weights["vwap_position"] * 0.67
                vwap_reason = "Price above VWAP"
            else:
                vwap_score = 0
                vwap_reason = "Price below VWAP"
            if setup_signal.get("vwap_reclaim"):
                vwap_score = weights["vwap_position"]
                vwap_reason = "Clean VWAP reclaim with volume"
        else:
            vwap_reason = "VWAP unavailable"
        factors.append(ScoreFactor("VWAP Position", vwap_score, weights["vwap_position"], vwap_reason))

        # Hard block: below VWAP trending down (except bottom_base)
        if vwap_pos == "below" and setup_type not in ("bottom_base", "fibonacci_pullback"):
            if indicators.get("lower_highs"):
                block_reasons.append("Price below VWAP with lower highs — downtrend")

        # ── 2. Key level behavior ─────────────────────────────────────────────
        kl_score = 0
        kl_reason = "No key level signal"
        if setup_signal.get("break_and_hold"):
            kl_score = weights["key_level_behavior"]
            kl_reason = "Break and hold above key level"
        elif setup_signal.get("near_key_level"):
            kl_score = weights["key_level_behavior"] * 0.5
            kl_reason = "Near key level"
        elif setup_signal.get("failed_key_level"):
            kl_score = 0
            block_reasons.append("Failed key level — price broke back under the level")
        factors.append(ScoreFactor("Key Level", kl_score, weights["key_level_behavior"], kl_reason))

        # ── 3. Volume confirmation ────────────────────────────────────────────
        rv = indicators.get("relative_volume", 0)
        if rv >= 3.0:
            vol_score = weights["volume_confirmation"]
            vol_reason = f"Relative volume {rv:.1f}x — strong"
        elif rv >= 2.0:
            vol_score = weights["volume_confirmation"] * 0.67
            vol_reason = f"Relative volume {rv:.1f}x — adequate"
        elif rv >= 1.5:
            vol_score = weights["volume_confirmation"] * 0.33
            vol_reason = f"Relative volume {rv:.1f}x — weak"
        else:
            vol_score = 0
            vol_reason = f"Relative volume {rv:.1f}x — insufficient"
        factors.append(ScoreFactor("Volume", vol_score, weights["volume_confirmation"], vol_reason))

        # ── 4. Market structure ───────────────────────────────────────────────
        if indicators.get("higher_lows"):
            ms_score = weights["market_structure"]
            ms_reason = "Higher lows visible — uptrend structure"
        elif not indicators.get("lower_highs"):
            ms_score = weights["market_structure"] * 0.5
            ms_reason = "Flat / sideways structure"
        else:
            ms_score = 0
            ms_reason = "Lower highs — downtrend structure"
        factors.append(ScoreFactor("Market Structure", ms_score, weights["market_structure"], ms_reason))

        # ── 5. RSI momentum ───────────────────────────────────────────────────
        rsi_val = indicators.get("rsi")
        if rsi_val is not None:
            if 55 <= rsi_val <= 75:
                rsi_score = weights["rsi_momentum"]
                rsi_reason = f"RSI {rsi_val:.0f} — bullish momentum zone"
            elif 45 <= rsi_val < 55:
                rsi_score = weights["rsi_momentum"] * 0.5
                rsi_reason = f"RSI {rsi_val:.0f} — neutral"
            elif rsi_val > 80:
                rsi_score = weights["rsi_momentum"] * 0.3
                rsi_reason = f"RSI {rsi_val:.0f} — overbought"
                if rsi_val > 85:
                    block_reasons.append(f"RSI {rsi_val:.0f} — extremely overbought without consolidation")
            else:
                rsi_score = 0
                rsi_reason = f"RSI {rsi_val:.0f} — bearish"
        else:
            rsi_score = 0
            rsi_reason = "RSI unavailable"
        factors.append(ScoreFactor("RSI", rsi_score, weights["rsi_momentum"], rsi_reason))

        # ── 6. MACD signal ────────────────────────────────────────────────────
        macd = indicators.get("macd") or {}
        if macd.get("bullish") and macd.get("histogram_direction") == "expanding":
            macd_score = weights["macd_signal"]
            macd_reason = "MACD bullish cross, histogram expanding"
        elif macd.get("bullish"):
            macd_score = weights["macd_signal"] * 0.5
            macd_reason = "MACD bullish"
        elif macd.get("crossover"):
            macd_score = weights["macd_signal"] * 0.75
            macd_reason = "MACD bullish crossover"
        else:
            macd_score = 0
            macd_reason = "MACD bearish or neutral"
        factors.append(ScoreFactor("MACD", macd_score, weights["macd_signal"], macd_reason))

        # ── 7. Fibonacci proximity ────────────────────────────────────────────
        fib_proximity = setup_signal.get("fib_proximity_pct")
        if fib_proximity is not None and fib_proximity <= 1.0:
            fib_score = weights["fibonacci_proximity"]
            fib_reason = f"Within {fib_proximity:.1f}% of Fibonacci level"
        elif fib_proximity is not None and fib_proximity <= 2.0:
            fib_score = weights["fibonacci_proximity"] * 0.6
            fib_reason = f"Within {fib_proximity:.1f}% of Fibonacci level"
        else:
            fib_score = 0
            fib_reason = "No Fibonacci confluence"
        factors.append(ScoreFactor("Fibonacci", fib_score, weights["fibonacci_proximity"], fib_reason))

        # ── 8. Opening range status ───────────────────────────────────────────
        or_status = setup_signal.get("opening_range_status", "unknown")
        if or_status == "above_orh_holding":
            or_score = weights["opening_range_status"]
            or_reason = "Above ORH with hold — strong"
        elif or_status == "approaching_orh":
            or_score = weights["opening_range_status"] * 0.5
            or_reason = "Approaching ORH"
        elif or_status == "below_orl":
            or_score = 0
            or_reason = "Below ORL — bearish"
        else:
            or_score = 0
            or_reason = "Opening range status unknown"
        factors.append(ScoreFactor("Opening Range", or_score, weights["opening_range_status"], or_reason))

        # ── 9. Liquidity sweep reclaim ────────────────────────────────────────
        if setup_signal.get("liquidity_sweep_reclaim"):
            ls_score = weights["liquidity_sweep"]
            ls_reason = "Clean liquidity sweep and reclaim"
        else:
            ls_score = 0
            ls_reason = "No liquidity sweep detected"
        factors.append(ScoreFactor("Liquidity Sweep", ls_score, weights["liquidity_sweep"], ls_reason))

        # ── 10. Catalyst/news quality ─────────────────────────────────────────
        cat_score_raw = news.get("score", 0)
        cat_score = weights["catalyst"] if cat_score_raw >= 3 else (weights["catalyst"] * 0.5 if cat_score_raw >= 2 else 0)
        cat_reason = f"Catalyst: {news.get('type', 'none')} — {news.get('headline', 'n/a')[:60] if news.get('headline') else 'none'}"
        factors.append(ScoreFactor("Catalyst", cat_score, weights["catalyst"], cat_reason))

        # ── Assemble result ───────────────────────────────────────────────────
        total = sum(f.score for f in factors)
        max_possible = sum(f.max_score for f in factors)
        normalized = (total / max_possible * 100) if max_possible > 0 else 0

        return SetupScoreResult(
            total_score=total,
            max_possible=max_possible,
            normalized=round(normalized, 1),
            factors=factors,
            hard_blocked=bool(block_reasons),
            block_reasons=block_reasons,
            setup_type=setup_type,
        )

    def _get_weights(self, setup_type: str) -> dict:
        profile = self.profiles.get(setup_type, {})
        return profile.get("score_weights", self.DEFAULT_WEIGHTS)
