"""
setups/base_setup.py — Shared interface all setup detectors inherit
Every setup returns a SetupResult with score, entry zone, stop, and targets.
Setup detectors IDENTIFY patterns — they do NOT score them (that's setup_score_engine).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SetupResult:
    detected: bool
    setup_type: str
    confidence: float              # 0.0 – 1.0 raw confidence from the detector
    entry_price: Optional[float]
    entry_zone_low: Optional[float]
    entry_zone_high: Optional[float]
    stop_price: Optional[float]
    initial_target: Optional[float]
    runner_target: Optional[float]
    targets: list[float] = field(default_factory=list)

    # Signal flags consumed by setup_score_engine
    signals: dict = field(default_factory=dict)
    # e.g. signals = {
    #   "vwap_reclaim": True,
    #   "break_and_hold": False,
    #   "fib_proximity_pct": 0.8,
    #   "opening_range_status": "above_orh_holding",
    #   "liquidity_sweep_reclaim": True,
    #   "near_key_level": False,
    #   "failed_key_level": False,
    # }

    rejection_reasons: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "detected": self.detected,
            "setup_type": self.setup_type,
            "confidence": self.confidence,
            "entry_price": self.entry_price,
            "entry_zone": [self.entry_zone_low, self.entry_zone_high],
            "stop_price": self.stop_price,
            "targets": self.targets,
            "signals": self.signals,
            "rejection_reasons": self.rejection_reasons,
            "description": self.description,
        }


class BaseSetup(ABC):
    """
    Abstract base class for all setup detectors.
    Each subclass implements detect() and returns a SetupResult.
    """

    def __init__(self, settings: dict, strategy_profiles: dict = None):
        self.settings = settings
        self.profiles = strategy_profiles or {}
        self.profile = self.profiles.get(self.setup_name, {})

    @property
    @abstractmethod
    def setup_name(self) -> str:
        """Unique identifier for this setup type."""
        ...

    @abstractmethod
    def detect(self, bars: list[dict], indicators: dict, context: dict) -> SetupResult:
        """
        Analyse the bar data and return a SetupResult.
        bars: list of OHLCV dicts
        indicators: output of indicator_calculator.compute_all()
        context: full context dict from bot_runner (includes news, market_state, etc.)
        """
        ...

    def _not_detected(self, reasons: list[str]) -> SetupResult:
        return SetupResult(
            detected=False,
            setup_type=self.setup_name,
            confidence=0.0,
            entry_price=None,
            entry_zone_low=None,
            entry_zone_high=None,
            stop_price=None,
            initial_target=None,
            runner_target=None,
            rejection_reasons=reasons,
        )
