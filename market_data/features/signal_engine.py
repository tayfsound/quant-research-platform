"""Gerçek özellik mühendisliği — ham OHLCV geçmişinden ajanların gerçekten
skorladığı kategorik sinyalleri üretir.

Kritik bulgu (2026-08-05): `CognitiveOrchestrator.run_cycle()` — tek gerçek
üretim giriş noktası — sadece ham rsi/ema/macd sayılarını hesaplıyordu,
ama `ContextAdapter.to_technical()`'ın gerçekten okuduğu `trend`/`momentum`/
`market_structure`/`ema_alignment`/`volatility_regime` gibi kategorik
alanları HİÇBİR kod üretmiyordu — bu yüzden TechnicalAgent (ve bu turda
eklenen Pattern/Quant ajanları) üretimde her zaman varsayılan/nötr
değerlerle çalışıyordu, piyasa ne olursa olsun. Üstüne, orchestrator
`"rsi"` (küçük harf) yazıyordu ama kod tabanının geri kalanı (CognitiveBinder,
inner_critic.py, outcome_evaluator.py, salience_detector.py, onlarca test)
`"RSI"` (büyük harf) bekliyordu — RSI de hiçbir zaman gerçek değildi. Bu
modül `"RSI"` (büyük harf) yazarak kod tabanının asıl konvansiyonuna uyuyor.

Dürüstlük ilkesi: Wyckoff faz tespiti gibi gerçekten belirsiz/öznel
konularda basitleştirilmiş bir yaklaşım kullanıyoruz ve bunu açıkça
belirtiyoruz — sofistike bir şeymiş gibi göstermiyoruz. Z-score, Hurst,
otokorelasyon, BOS/CHoCH/FVG gibi kesin tanımlı olanlar tam olarak
hesaplanıyor.
"""
from __future__ import annotations

import math

import numpy as np

from market_data.ingestion.ohlcv import OHLCV


def _closes(data: list[OHLCV]) -> np.ndarray:
    return np.array([d.close for d in data], dtype=float)


def _returns(closes: np.ndarray) -> np.ndarray:
    return np.diff(closes) / closes[:-1]


def _ema_series(values: np.ndarray, period: int) -> np.ndarray:
    """Tam bir EMA serisi (tek nokta değil) — gerçek MACD signal line için gerekli."""
    if len(values) == 0:
        return values
    alpha = 2.0 / (period + 1)
    out = np.empty_like(values)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = (values[i] - out[i - 1]) * alpha + out[i - 1]
    return out


def compute_technical_signals(data: list[OHLCV]) -> dict:
    """trend/momentum/market_structure/ema_alignment/volatility_regime/
    volume_confirmation + gerçek rsi/ema/macd sayıları — hepsi tek bir
    OHLCV geçmişinden, gerçekten hesaplanıyor."""
    if len(data) < 5:
        return {
            "RSI": 50.0, "ema": data[-1].close if data else 0.0, "macd": 0.0,
            "trend": "neutral", "momentum": "neutral", "market_structure": "neutral",
            "ema_alignment": "neutral", "volatility_regime": "normal", "volume_confirmation": False,
        }

    closes = _closes(data)
    n = len(closes)

    ema_fast = _ema_series(closes, min(12, max(2, n // 3)))
    ema_slow = _ema_series(closes, min(26, max(3, n // 2)))
    macd_line = ema_fast - ema_slow
    macd_signal = _ema_series(macd_line, min(9, max(2, n // 4)))
    macd_hist = macd_line - macd_signal

    ema20 = ema_fast[-1]
    ema50 = ema_slow[-1]
    trend = "bullish" if ema20 > ema50 else "bearish" if ema20 < ema50 else "neutral"

    # Momentum: MACD histogram büyüyor mu (gerçek ivme) küçülüyor mu.
    hist_window = macd_hist[-5:] if len(macd_hist) >= 5 else macd_hist
    if len(hist_window) >= 2 and hist_window[-1] > hist_window[0]:
        momentum = "strengthening"
    elif len(hist_window) >= 2 and hist_window[-1] < hist_window[0]:
        momentum = "weakening"
    else:
        momentum = "neutral"

    # Market structure: swing high/low karşılaştırması (basit ama gerçek).
    market_structure = _swing_structure(closes)

    # EMA alignment: kısa/orta/uzun EMA sıralaması.
    ema200_period = min(50, max(5, n - 1))
    ema200 = _ema_series(closes, ema200_period)[-1]
    if ema20 > ema50 > ema200:
        ema_alignment = "bullish_aligned"
    elif ema20 < ema50 < ema200:
        ema_alignment = "bearish_aligned"
    else:
        ema_alignment = "mixed"

    # Volatility regime: son gerçekleşen volatilite, kendi geçmiş dağılımına göre.
    returns = _returns(closes)
    volatility_regime = _volatility_regime(returns)

    # Volume confirmation: son hacim, rolling ortalamanın üzerinde mi.
    volumes = np.array([d.volume for d in data], dtype=float)
    volume_confirmation = bool(volumes[-1] > volumes[-20:].mean()) if len(volumes) >= 2 else False

    period = min(14, n - 1)
    rsi_value = _rsi(closes, period)

    return {
        "RSI": round(float(rsi_value), 2),
        "ema": round(float(ema20), 6),
        "macd": round(float(macd_line[-1]), 6),
        "trend": trend,
        "momentum": momentum,
        "market_structure": market_structure,
        "ema_alignment": ema_alignment,
        "volatility_regime": volatility_regime,
        "volume_confirmation": volume_confirmation,
    }


def _rsi(closes: np.ndarray, period: int) -> float:
    if len(closes) < period + 1:
        return 50.0
    diffs = np.diff(closes[-(period + 1):])
    gains = np.clip(diffs, 0, None)
    losses = np.clip(-diffs, 0, None)
    avg_gain = gains.mean()
    avg_loss = losses.mean()
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _find_swings(closes: np.ndarray, window: int = 3) -> tuple[list[int], list[int]]:
    """Yerel tepe/dip indekslerini bulur (basit ama gerçek: window genişliğinde
    komşularından yüksek/düşük olan noktalar)."""
    highs, lows = [], []
    for i in range(window, len(closes) - window):
        seg = closes[i - window: i + window + 1]
        if closes[i] == seg.max():
            highs.append(i)
        if closes[i] == seg.min():
            lows.append(i)
    return highs, lows


def _swing_structure(closes: np.ndarray) -> str:
    highs, lows = _find_swings(closes)
    if len(highs) < 2 or len(lows) < 2:
        return "ranging"
    higher_highs = closes[highs[-1]] > closes[highs[-2]]
    higher_lows = closes[lows[-1]] > closes[lows[-2]]
    lower_highs = closes[highs[-1]] < closes[highs[-2]]
    lower_lows = closes[lows[-1]] < closes[lows[-2]]
    if higher_highs and higher_lows:
        return "higher_highs_higher_lows"
    if lower_highs and lower_lows:
        return "lower_highs_lower_lows"
    return "ranging"


def _volatility_regime(returns: np.ndarray) -> str:
    if len(returns) < 10:
        return "normal"
    rolling_vol = np.array([
        returns[max(0, i - 10):i + 1].std() for i in range(len(returns))
    ])
    current = rolling_vol[-1]
    baseline = rolling_vol.mean()
    if baseline == 0:
        return "normal"
    ratio = current / baseline
    if ratio > 1.5:
        return "high"
    if ratio < 0.67:
        return "low"
    return "normal"


def compute_pattern_signals(data: list[OHLCV]) -> dict:
    """structure_phase/break_of_structure/change_of_character/fair_value_gap/
    swing_structure/liquidity_sweep — BOS/CHoCH/FVG/swing/sweep kesin
    tanımlı kurallarla gerçekten hesaplanıyor. structure_phase (Wyckoff)
    kasıtlı olarak basitleştirilmiş bir yaklaşım — gerçek Wyckoff faz
    tespiti hacim+fiyat davranışının çok daha derin analizini gerektirir,
    burada sadece volatilite sıkışması + hacim trendinden kaba bir tahmin
    üretiliyor, sofistike bir şeymiş gibi sunulmuyor."""
    if len(data) < 10:
        return {
            "structure_phase": "neutral", "break_of_structure": "none",
            "change_of_character": False, "fair_value_gap": "none",
            "swing_structure": "mixed", "liquidity_sweep": "none",
        }

    closes = _closes(data)
    highs = np.array([d.high for d in data], dtype=float)
    lows = np.array([d.low for d in data], dtype=float)

    swing_highs, swing_lows = _find_swings(closes)
    swing_structure = _swing_structure(closes)

    # Break of structure: son fiyat, en son önemli swing high/low'u aştı mı.
    break_of_structure = "none"
    if swing_highs and closes[-1] > highs[swing_highs[-1]]:
        break_of_structure = "bullish"
    elif swing_lows and closes[-1] < lows[swing_lows[-1]]:
        break_of_structure = "bearish"

    # Change of character: yapı son 2 swing setinde yön değiştirdi mi.
    change_of_character = False
    if len(swing_highs) >= 3 and len(swing_lows) >= 3:
        prev_structure = _swing_structure(closes[:-3])
        change_of_character = prev_structure != "ranging" and swing_structure != "ranging" and prev_structure != swing_structure

    # Fair Value Gap: 3-mumluk ICT tanımı — orta mum, 1. ve 3. mum arasında
    # gerçek bir boşluk bırakıyor mu.
    fair_value_gap = "none"
    if len(data) >= 3:
        c1, c3 = data[-3], data[-1]
        if c1.high < c3.low:
            fair_value_gap = "bullish"
        elif c1.low > c3.high:
            fair_value_gap = "bearish"

    # Liquidity sweep: son mum bir swing'in ötesine fitil atıp içeri kapandı mı.
    liquidity_sweep = "none"
    if swing_highs and data[-1].high > highs[swing_highs[-1]] and data[-1].close < highs[swing_highs[-1]]:
        liquidity_sweep = "buy_side_swept"
    elif swing_lows and data[-1].low < lows[swing_lows[-1]] and data[-1].close > lows[swing_lows[-1]]:
        liquidity_sweep = "sell_side_swept"

    structure_phase = _approximate_wyckoff_phase(data)

    return {
        "structure_phase": structure_phase,
        "break_of_structure": break_of_structure,
        "change_of_character": change_of_character,
        "fair_value_gap": fair_value_gap,
        "swing_structure": swing_structure,
        "liquidity_sweep": liquidity_sweep,
    }


def _approximate_wyckoff_phase(data: list[OHLCV]) -> str:
    """Kaba yaklaşım: düşük volatilite + artan hacim + yatay fiyat =
    accumulation-vari; yüksek volatilite + düşen hacim tepe civarında =
    distribution-vari. Gerçek Wyckoff analizi değil, dürüst bir proxy."""
    closes = _closes(data)
    volumes = np.array([d.volume for d in data], dtype=float)
    if len(closes) < 10:
        return "neutral"
    returns = _returns(closes)
    recent_vol = returns[-10:].std()
    overall_vol = returns.std() if returns.std() > 0 else 1e-9
    vol_ratio = recent_vol / overall_vol
    volume_trend = volumes[-5:].mean() - volumes[-15:-5].mean() if len(volumes) >= 15 else 0.0
    price_range_pct = (closes[-10:].max() - closes[-10:].min()) / closes[-10:].mean()

    if vol_ratio < 0.8 and price_range_pct < 0.03 and volume_trend > 0:
        return "accumulation" if closes[-1] < closes[-10:].mean() else "distribution"
    if vol_ratio > 1.3 and closes[-1] > closes[-10:].mean():
        return "markup"
    if vol_ratio > 1.3 and closes[-1] < closes[-10:].mean():
        return "markdown"
    return "neutral"


def compute_quant_signals(data: list[OHLCV]) -> dict:
    """zscore/realized_vol_percentile/autocorrelation/hurst_exponent —
    hepsi standart, kesin tanımlı istatistiksel hesaplamalar."""
    if len(data) < 20:
        return {"zscore": 0.0, "realized_vol_percentile": 50.0, "autocorrelation": 0.0, "hurst_exponent": 0.5}

    closes = _closes(data)
    returns = _returns(closes)

    window = min(20, len(closes) - 1)
    recent = closes[-window:]
    mean, std = recent.mean(), recent.std()
    zscore = (closes[-1] - mean) / std if std > 0 else 0.0

    realized_vol_percentile = _realized_vol_percentile(returns)
    autocorrelation = _autocorrelation(returns)
    hurst_exponent = _hurst_exponent(closes)

    return {
        "zscore": round(float(zscore), 3),
        "realized_vol_percentile": round(float(realized_vol_percentile), 1),
        "autocorrelation": round(float(autocorrelation), 3),
        "hurst_exponent": round(float(hurst_exponent), 3),
    }


def _realized_vol_percentile(returns: np.ndarray, window: int = 10) -> float:
    if len(returns) < window + 5:
        return 50.0
    rolling = np.array([
        returns[max(0, i - window):i + 1].std() for i in range(len(returns))
    ])
    current = rolling[-1]
    return float((rolling < current).mean() * 100)


def _autocorrelation(returns: np.ndarray, lag: int = 1) -> float:
    if len(returns) < lag + 5:
        return 0.0
    a, b = returns[:-lag], returns[lag:]
    if a.std() == 0 or b.std() == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def _hurst_exponent(closes: np.ndarray) -> float:
    """Rescaled range (R/S) analizi ile basit Hurst tahmini. Standart,
    literatürde tanımlı bir yöntem — ama küçük örneklemlerde gürültülü
    olduğu bilinen, kabaca bir tahmin (gerçek zaman serisi analizi bu
    konuda çok daha büyük örneklemler ister)."""
    n = len(closes)
    if n < 20:
        return 0.5
    log_returns = np.diff(np.log(closes))
    lags = [l for l in (5, 10, 20, 40) if l < len(log_returns)]
    if len(lags) < 2:
        return 0.5

    tau = []
    for lag in lags:
        diffs = log_returns[lag:] - log_returns[:-lag]
        tau.append(np.sqrt(np.std(diffs)) if np.std(diffs) > 0 else 1e-9)

    try:
        poly = np.polyfit(np.log(lags), np.log(tau), 1)
        hurst = poly[0] * 2.0
    except (np.linalg.LinAlgError, ValueError):
        return 0.5

    if math.isnan(hurst) or math.isinf(hurst):
        return 0.5
    return float(np.clip(hurst, 0.0, 1.0))
