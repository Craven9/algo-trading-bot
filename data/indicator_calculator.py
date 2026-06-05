"""
data/indicator_calculator.py — Technical indicator calculations
Computes RSI, MACD, VWAP, MAs, ATR, and relative volume from OHLCV bars.
All functions are pure — they take bar data and return values. No side effects.
"""

import logging
import math
from typing import Optional

log = logging.getLogger(__name__)


def extract_series(bars: list[dict], field: str) -> list[float]:
    return [b[field] for b in bars if field in b]


# ── Moving Averages ───────────────────────────────────────────────────────────

def sma(values: list[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema(values: list[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    result = sum(values[:period]) / period  # seed with SMA
    for v in values[period:]:
        result = v * k + result * (1 - k)
    return result


def ema_series(values: list[float], period: int) -> list[float]:
    """Return a full EMA series (same length as input, with NaN for early bars)."""
    if len(values) < period:
        return [float("nan")] * len(values)
    k = 2 / (period + 1)
    emas = [float("nan")] * (period - 1)
    seed = sum(values[:period]) / period
    emas.append(seed)
    for v in values[period:]:
        emas.append(v * k + emas[-1] * (1 - k))
    return emas


# ── RSI ───────────────────────────────────────────────────────────────────────

def rsi(closes: list[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# ── MACD ──────────────────────────────────────────────────────────────────────

def macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Optional[dict]:
    if len(closes) < slow + signal:
        return None
    ema_fast = ema_series(closes, fast)
    ema_slow = ema_series(closes, slow)

    macd_line = [
        f - s if not (math.isnan(f) or math.isnan(s)) else float("nan")
        for f, s in zip(ema_fast, ema_slow)
    ]

    valid_macd = [v for v in macd_line if not math.isnan(v)]
    if len(valid_macd) < signal:
        return None

    signal_line = ema_series(valid_macd, signal)
    latest_signal = signal_line[-1]
    latest_macd = valid_macd[-1]
    histogram = latest_macd - latest_signal

    # Previous histogram for direction
    prev_histogram = valid_macd[-2] - signal_line[-2] if len(signal_line) >= 2 else 0

    return {
        "macd": latest_macd,
        "signal": latest_signal,
        "histogram": histogram,
        "histogram_direction": "expanding" if abs(histogram) > abs(prev_histogram) else "contracting",
        "crossover": latest_macd > latest_signal and valid_macd[-2] <= signal_line[-2] if len(valid_macd) >= 2 else False,
        "bullish": latest_macd > latest_signal,
    }


# ── VWAP ──────────────────────────────────────────────────────────────────────

def vwap(bars: list[dict], session_bars_only: bool = True) -> Optional[float]:
    """
    Compute VWAP for the current session.
    Expects bars with keys: h, l, c, v (high, low, close, volume).
    """
    if not bars:
        return None

    total_pv = 0.0
    total_v = 0.0
    for b in bars:
        typical = (b["h"] + b["l"] + b["c"]) / 3
        vol = b.get("v", 0)
        total_pv += typical * vol
        total_v += vol

    return total_pv / total_v if total_v > 0 else None


# ── ATR ───────────────────────────────────────────────────────────────────────

def atr(bars: list[dict], period: int = 14) -> Optional[float]:
    if len(bars) < period + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        h = bars[i]["h"]
        l = bars[i]["l"]
        prev_c = bars[i - 1]["c"]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)

    if len(trs) < period:
        return None

    # Wilder smoothing
    atr_val = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr_val = (atr_val * (period - 1) + tr) / period
    return atr_val


# ── Volume ────────────────────────────────────────────────────────────────────

def relative_volume(bars: list[dict], lookback: int = 20) -> float:
    """Current bar volume vs. average of prior N bars."""
    if len(bars) < 2:
        return 0.0
    current = bars[-1].get("v", 0)
    prior = bars[-(lookback + 1):-1]
    avg = sum(b["v"] for b in prior) / len(prior) if prior else 1
    return current / avg if avg > 0 else 0.0


def volume_trend(bars: list[dict], lookback: int = 5) -> str:
    """Returns 'increasing', 'decreasing', or 'flat'."""
    if len(bars) < lookback:
        return "flat"
    vols = [b["v"] for b in bars[-lookback:]]
    mid = len(vols) // 2
    first_half_avg = sum(vols[:mid]) / mid
    second_half_avg = sum(vols[mid:]) / (len(vols) - mid)
    if second_half_avg > first_half_avg * 1.1:
        return "increasing"
    if second_half_avg < first_half_avg * 0.9:
        return "decreasing"
    return "flat"


# ── Market structure ──────────────────────────────────────────────────────────

def find_swing_highs(bars: list[dict], lookback: int = 3) -> list[float]:
    highs = []
    for i in range(lookback, len(bars) - lookback):
        if all(bars[i]["h"] > bars[j]["h"] for j in range(i - lookback, i + lookback + 1) if j != i):
            highs.append(bars[i]["h"])
    return highs


def find_swing_lows(bars: list[dict], lookback: int = 3) -> list[float]:
    lows = []
    for i in range(lookback, len(bars) - lookback):
        if all(bars[i]["l"] < bars[j]["l"] for j in range(i - lookback, i + lookback + 1) if j != i):
            lows.append(bars[i]["l"])
    return lows


def detect_higher_lows(bars: list[dict], count: int = 3) -> bool:
    lows = find_swing_lows(bars)
    if len(lows) < count:
        return False
    recent = lows[-count:]
    return all(recent[i] > recent[i - 1] for i in range(1, len(recent)))


def detect_lower_highs(bars: list[dict], count: int = 3) -> bool:
    highs = find_swing_highs(bars)
    if len(highs) < count:
        return False
    recent = highs[-count:]
    return all(recent[i] < recent[i - 1] for i in range(1, len(recent)))


# ── Master indicator bundle ───────────────────────────────────────────────────

def compute_all(bars: list[dict], settings: dict) -> dict:
    """
    Compute all indicators for a bar set and return as a single dict.
    This is the main entry point for the analysis engines.
    """
    if not bars:
        return {}

    cfg = settings.get("indicators", {})
    closes = extract_series(bars, "c")
    volumes = extract_series(bars, "v")

    vwap_val = vwap(bars)
    latest_close = closes[-1] if closes else 0

    return {
        "vwap": vwap_val,
        "price_vs_vwap": "above" if vwap_val and latest_close > vwap_val else "below",
        "vwap_distance_pct": ((latest_close - vwap_val) / vwap_val * 100) if vwap_val else 0,
        "rsi": rsi(closes, cfg.get("rsi_period", 14)),
        "macd": macd(
            closes,
            cfg.get("macd_fast", 12),
            cfg.get("macd_slow", 26),
            cfg.get("macd_signal", 9),
        ),
        "atr": atr(bars, cfg.get("atr_period", 14)),
        "ma_fast": ema(closes, cfg.get("ma_fast", 9)),
        "ma_slow": ema(closes, cfg.get("ma_slow", 20)),
        "relative_volume": relative_volume(bars, cfg.get("volume_ma_period", 20)),
        "volume_trend": volume_trend(bars),
        "higher_lows": detect_higher_lows(bars),
        "lower_highs": detect_lower_highs(bars),
        "swing_highs": find_swing_highs(bars),
        "swing_lows": find_swing_lows(bars),
        "latest_close": latest_close,
        "latest_bar": bars[-1],
    }
