"""
decision/trade_quality_gate.py — Master buy/no-buy decision engine
Assembles all scores, checks all conditions, outputs a verdict with full explanation.
This is the ONLY place that makes the final trade entry decision.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import data.indicator_calculator as ind
from analysis.setup_score_engine import SetupScoreEngine, SetupScoreResult
from analysis.probability_engine import ProbabilityEngine
from analysis.fibonacci_engine import FibonacciEngine
from analysis.move_potential_engine import MovePotentialEngine
from analysis.opening_range_analyzer import OpeningRangeAnalyzer
from analysis.liquidity_sweep_detector import LiquiditySweepDetector
from analysis.session_structure_analyzer import SessionStructureAnalyzer
from analysis.market_influence_filter import MarketInfluenceFilter
from setups.break_and_hold import BreakAndHold
from setups.vwap_reclaim import VWAPReclaim
from setups.bottom_base import BottomBase
from setups.fibonacci_pullback import FibonacciPullback
from setups.opening_range_breakout import OpeningRangeBreakout
from risk.risk_manager import RiskManager
from config.settings_loader import load_strategy_profiles

log = logging.getLogger(__name__)


@dataclass
class TradeVerdict:
    approved: bool
    ticker: str
    setup_type: str
    setup_score: float
    probability: float
    risk_reward: float
    entry_price: float
    stop_price: float
    position_size: int
    targets: list[float]
    approval_reasons: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    score_breakdown: dict = field(default_factory=dict)
    probability_breakdown: dict = field(default_factory=dict)

    @property
    def primary_rejection_reason(self) -> str:
        return self.rejection_reasons[0] if self.rejection_reasons else "Unknown"

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "ticker": self.ticker,
            "setup_type": self.setup_type,
            "setup_score": self.setup_score,
            "probability_pct": round(self.probability * 100, 1),
            "risk_reward": self.risk_reward,
            "entry_price": self.entry_price,
            "stop_price": self.stop_price,
            "position_size": self.position_size,
            "targets": self.targets,
            "approval_reasons": self.approval_reasons,
            "rejection_reasons": self.rejection_reasons,
            "score_breakdown": self.score_breakdown,
            "probability_breakdown": self.probability_breakdown,
        }


class TradeQualityGate:
    """
    Runs the full 7-phase evaluation pipeline for each candidate.
    Assembles all engines and applies every hard rule and preference.
    Returns a TradeVerdict — never modifies state or places orders.
    """

    SETUP_DETECTORS = {
        "break_and_hold":       BreakAndHold,
        "vwap_reclaim":         VWAPReclaim,
        "bottom_base":          BottomBase,
        "fibonacci_pullback":   FibonacciPullback,
        "opening_range_breakout": OpeningRangeBreakout,
    }

    def __init__(self, settings: dict, performance_tracker=None):
        self.settings = settings
        self.profiles = load_strategy_profiles()
        self.entry_cfg = settings["entry"]
        self.market_filter = MarketInfluenceFilter(settings, None)  # data fetcher set later

        self.score_engine = SetupScoreEngine(settings, self.profiles)
        self.prob_engine   = ProbabilityEngine(settings, performance_tracker)
        self.fib_engine    = FibonacciEngine(settings)
        self.move_engine   = MovePotentialEngine(settings)
        self.or_analyzer   = OpeningRangeAnalyzer(settings)
        self.sweep_detector = LiquiditySweepDetector(settings)
        self.structure_analyzer = SessionStructureAnalyzer(settings)
        self.risk_manager  = RiskManager(settings)

        # Initialise setup detectors
        self.detectors = {
            name: cls(settings, self.profiles)
            for name, cls in self.SETUP_DETECTORS.items()
            if settings["setups"].get(name, {}).get("enabled", True)
        }

    def evaluate(self, context: dict) -> TradeVerdict:
        """
        Full pipeline evaluation. Returns a TradeVerdict regardless of outcome.
        context keys: ticker, ohlcv, level2, news, market_state, account_state, timestamp
        """
        ticker = context["ticker"]
        ohlcv  = context["ohlcv"]
        bars   = ohlcv["bars"]
        level2 = context.get("level2") or {}
        news   = context.get("news") or {}
        market_state = context.get("market_state") or {}
        account_state = context.get("account_state") or {}

        rejection_reasons = []

        # ── Phase 1: Fast blockers ──────────────────────────────────────────

        # Spread check
        spread_pct = level2.get("spread_pct", 0)
        max_spread = self.settings["execution"]["max_spread_pct"]
        if spread_pct > max_spread:
            rejection_reasons.append(f"Spread {spread_pct:.2f}% exceeds max {max_spread}%")
            return self._reject(ticker, rejection_reasons)

        # Relative volume check
        rv = ohlcv.get("relative_volume", 0)
        min_rv = self.settings["scanner"]["min_relative_volume"]
        if rv < min_rv:
            rejection_reasons.append(f"Relative volume {rv:.1f}x below minimum {min_rv}x")
            return self._reject(ticker, rejection_reasons)

        # Market state check
        market_ok, market_reason = self._check_market(market_state)
        if not market_ok:
            rejection_reasons.append(market_reason)
            return self._reject(ticker, rejection_reasons)

        # Account state check
        account_ok, account_reason = self._check_account(account_state)
        if not account_ok:
            rejection_reasons.append(account_reason)
            return self._reject(ticker, rejection_reasons)

        # ── Phase 2: Technical analysis ──────────────────────────────────────

        indicators = ind.compute_all(bars, self.settings)
        structure  = self.structure_analyzer.analyze(bars)
        fib_result = self.fib_engine.calculate(bars, indicators.get("latest_close", 0))
        or_status  = self.or_analyzer.get_or_status(bars, indicators.get("latest_close", 0))

        # Liquidity sweep against key support levels
        support_levels = structure.support_levels or []
        if indicators.get("vwap"):
            support_levels = support_levels + [indicators["vwap"]]
        sweep = self.sweep_detector.detect(bars, support_levels)

        # Build setup_signal dict (used by score engine and setup detectors)
        setup_signal = {
            "vwap_reclaim":          self._check_vwap_reclaim(bars, indicators),
            "break_and_hold":        False,  # set by detector
            "near_key_level":        False,
            "failed_key_level":      False,
            "liquidity_sweep_reclaim": sweep.detected and sweep.reclaimed,
            "opening_range_status":  or_status,
            "fib_proximity_pct":     fib_result.proximity_pct if fib_result else None,
        }
        context["setup_signal"] = setup_signal
        context["indicators"]   = indicators
        context["structure"]    = structure
        context["fib_result"]   = fib_result

        # ── Phase 3: Setup detection ──────────────────────────────────────────

        best_setup = None
        for name, detector in self.detectors.items():
            result = detector.detect(bars, indicators, context)
            if result.detected:
                if best_setup is None or result.confidence > best_setup.confidence:
                    best_setup = result
                    # Merge detector signals back into context
                    setup_signal.update(result.signals)

        if not best_setup:
            rejection_reasons.append("No setup pattern detected")
            return self._reject(ticker, rejection_reasons)

        # ── Phase 4: Scoring ──────────────────────────────────────────────────

        context["setup_signal"] = setup_signal
        score_result = self.score_engine.score(context, best_setup.setup_type)

        if score_result.hard_blocked:
            rejection_reasons.extend(score_result.block_reasons)
            return self._reject(ticker, rejection_reasons)

        min_score = self.settings["setups"].get(best_setup.setup_type, {}).get("min_score", self.entry_cfg["min_setup_score"])
        if score_result.normalized < min_score:
            rejection_reasons.append(f"Setup score {score_result.normalized:.0f} below minimum {min_score}")
            return self._reject(ticker, rejection_reasons, score_result.to_dict())

        # ── Phase 5: Probability ──────────────────────────────────────────────

        prob_result = self.prob_engine.estimate(score_result.normalized, context, best_setup.setup_type)
        if not prob_result["passes_threshold"]:
            rejection_reasons.append(
                f"Probability {prob_result['probability_pct']:.0f}% below minimum {self.entry_cfg['min_probability']}%"
            )
            return self._reject(ticker, rejection_reasons, score_result.to_dict(), prob_result)

        # ── Phase 6: Risk / Reward ────────────────────────────────────────────

        entry_price = best_setup.entry_price
        stop_price  = best_setup.stop_price
        targets     = best_setup.targets

        if not entry_price or not stop_price:
            rejection_reasons.append("Setup did not produce valid entry/stop prices")
            return self._reject(ticker, rejection_reasons)

        move = self.move_engine.calculate(entry_price, stop_price, targets, indicators.get("atr"))
        if not move.passes_rr_minimum:
            rejection_reasons.append(f"R:R {move.risk_reward:.1f} below minimum {self.entry_cfg['min_risk_reward']}")
            return self._reject(ticker, rejection_reasons, score_result.to_dict(), prob_result)

        # ── Phase 7: Position sizing ──────────────────────────────────────────

        account_balance = account_state.get("equity", 100_000)
        shares = self.risk_manager.calculate_shares(
            account_balance=account_balance,
            entry_price=entry_price,
            stop_price=stop_price,
            atr=indicators.get("atr"),
            setup_score=score_result.normalized,
        )

        if shares <= 0:
            rejection_reasons.append("Position size calculated as 0 — risk parameters too tight")
            return self._reject(ticker, rejection_reasons)

        # ── APPROVED ─────────────────────────────────────────────────────────

        approval_reasons = [
            f"Setup: {best_setup.setup_type} ({best_setup.description})",
            f"Score: {score_result.normalized:.0f}/100",
            f"Probability: {prob_result['probability_pct']:.0f}%",
            f"R:R: {move.risk_reward:.1f}",
            f"Entry: ${entry_price:.2f} | Stop: ${stop_price:.2f}",
            f"Position: {shares} shares",
        ]
        if news.get("has_catalyst"):
            approval_reasons.append(f"Catalyst: {news.get('headline', '')[:60]}")

        log.info(f"APPROVED {ticker} | {best_setup.setup_type} | score={score_result.normalized:.0f} prob={prob_result['probability_pct']:.0f}% RR={move.risk_reward:.1f}")

        return TradeVerdict(
            approved=True,
            ticker=ticker,
            setup_type=best_setup.setup_type,
            setup_score=score_result.normalized,
            probability=prob_result["probability"],
            risk_reward=move.risk_reward,
            entry_price=entry_price,
            stop_price=stop_price,
            position_size=shares,
            targets=targets,
            approval_reasons=approval_reasons,
            score_breakdown=score_result.to_dict(),
            probability_breakdown=prob_result,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _reject(self, ticker: str, reasons: list[str], score: dict = None, prob: dict = None) -> TradeVerdict:
        return TradeVerdict(
            approved=False,
            ticker=ticker,
            setup_type="none",
            setup_score=0,
            probability=0,
            risk_reward=0,
            entry_price=0,
            stop_price=0,
            position_size=0,
            targets=[],
            rejection_reasons=reasons,
            score_breakdown=score or {},
            probability_breakdown=prob or {},
        )

    def _check_market(self, market_state: dict) -> tuple[bool, str]:
        if market_state.get("block_entries"):
            return False, "Market conditions blocking entries"
        if market_state.get("bias") == "bearish":
            return False, "Broad market bearish — no long entries"
        return True, "OK"

    def _check_account(self, account_state: dict) -> tuple[bool, str]:
        if account_state.get("daily_loss_limit_hit"):
            return False, "Daily loss limit reached — no new entries today"
        if account_state.get("max_positions_hit"):
            return False, "Maximum open positions reached"
        if account_state.get("max_exposure_hit"):
            return False, "Maximum portfolio exposure reached"
        return True, "OK"

    def _check_vwap_reclaim(self, bars: list[dict], indicators: dict) -> bool:
        vwap = indicators.get("vwap")
        if not vwap:
            return False
        price = indicators.get("latest_close", 0)
        if price <= vwap:
            return False
        # At least one recent bar dipped below VWAP
        return any(b["c"] < vwap for b in bars[-6:-1])
