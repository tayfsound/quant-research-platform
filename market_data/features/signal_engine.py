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
            "atr": 0.0,
            "bollinger_percent_b": 0.5, "bollinger_bandwidth": 0.0, "vwap_deviation_pct": 0.0,
            "adx": 0.0, "di_plus": 0.0, "di_minus": 0.0,
            "obv_trend": "flat", "price_obv_divergence": "none",
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
    atr_value = _atr(data, min(14, n - 1))

    # Faz 237: kullanıcı isteği — "eklenebilecek bütün teknik analiz
    # yöntemlerini ekleyelim eğer matematiksel bir yöntemse." Bollinger/
    # VWAP/ADX/OBV — dördü de kesin tanımlı, standart formüller (Stochastic/
    # Williams %R/CCI kasıtlı olarak eklenmedi: RSI'ın zaten kapsadığı
    # "aşırı alım/satım" fikrini büyük ölçüde tekrarlıyorlar, katma değerleri
    # düşük; Parabolic SAR/Keltner/Donchian de mevcut trend/ATR/swing
    # göstergeleriyle ciddi örtüşüyor).
    bollinger_percent_b, bollinger_bandwidth = _bollinger_bands(closes)
    vwap_deviation_pct = _vwap_deviation(data)
    adx_value, di_plus, di_minus = _adx(data, min(14, n - 1))
    obv_trend, price_obv_divergence = _obv_signal(closes, volumes)

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
        "atr": round(float(atr_value), 6),
        "bollinger_percent_b": round(float(bollinger_percent_b), 3),
        "bollinger_bandwidth": round(float(bollinger_bandwidth), 4),
        "vwap_deviation_pct": round(float(vwap_deviation_pct), 4),
        "adx": round(float(adx_value), 2),
        "di_plus": round(float(di_plus), 2),
        "di_minus": round(float(di_minus), 2),
        "obv_trend": obv_trend,
        "price_obv_divergence": price_obv_divergence,
    }


def _bollinger_bands(closes: np.ndarray, period: int = 20, k: float = 2.0) -> tuple[float, float]:
    """Standart Bollinger Bands — SMA ± k*std. percent_b: fiyatın bantlar
    arasındaki konumu (0=alt bant, 1=üst bant, aralık dışına da çıkabilir).
    bandwidth: bantların SMA'ya göre göreli genişliği (düşük = sıkışma,
    genelde bir sonraki büyük harekete işaret eder)."""
    window = min(period, len(closes))
    if window < 2:
        return 0.5, 0.0
    recent = closes[-window:]
    sma = recent.mean()
    std = recent.std()
    upper, lower = sma + k * std, sma - k * std
    band_range = upper - lower
    percent_b = (closes[-1] - lower) / band_range if band_range > 0 else 0.5
    bandwidth = band_range / sma if sma > 0 else 0.0
    return percent_b, bandwidth


def _vwap_deviation(data: list[OHLCV]) -> float:
    """Volume-Weighted Average Price — standart formül (typical price ×
    hacim / toplam hacim). Gerçek bir "session" kavramı olmadığı için
    (bu proje 7/24 kripto + hisse karışık takip ediyor) mevcut lookback
    penceresinin tamamı "session" olarak kullanılıyor — dürüst bir
    yaklaşıklama, gerçek borsa session VWAP'ı değil, açıkça belirtiliyor.
    Dönen değer: fiyatın VWAP'a göre göreli sapması (%)."""
    typical_prices = np.array([(d.high + d.low + d.close) / 3.0 for d in data], dtype=float)
    volumes = np.array([d.volume for d in data], dtype=float)
    total_volume = volumes.sum()
    if total_volume <= 0:
        return 0.0
    vwap = float((typical_prices * volumes).sum() / total_volume)
    if vwap <= 0:
        return 0.0
    return (data[-1].close - vwap) / vwap


def _adx(data: list[OHLCV], period: int) -> tuple[float, float, float]:
    """Average Directional Index (Wilder, standart tanım) — trend YÖNÜNÜ
    değil trend GÜCÜNÜ ölçer (ADX>25 güçlü trend, <20 zayıf/yatay —
    literatürdeki standart eşikler). Sistemdeki hiçbir mevcut gösterge
    bunu ölçmüyordu: Hurst istatistiksel bir rejim ayrımı yapıyor
    (mean-reverting vs trending), ADX ise "şu an gerçekten güçlü bir
    trend içindeyiz" sorusuna kesin tanımlı, farklı bir cevap veriyor."""
    if len(data) < period + 2 or period < 1:
        return 0.0, 0.0, 0.0

    highs = np.array([d.high for d in data], dtype=float)
    lows = np.array([d.low for d in data], dtype=float)
    closes = np.array([d.close for d in data], dtype=float)

    up_move = highs[1:] - highs[:-1]
    down_move = lows[:-1] - lows[1:]
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    prev_closes = closes[:-1]
    true_ranges = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(np.abs(highs[1:] - prev_closes), np.abs(lows[1:] - prev_closes)),
    )

    def _wilder_smooth(values: np.ndarray, p: int) -> np.ndarray:
        if len(values) < p:
            return values
        smoothed = np.empty(len(values) - p + 1)
        smoothed[0] = values[:p].sum()
        for i in range(1, len(smoothed)):
            smoothed[i] = smoothed[i - 1] - (smoothed[i - 1] / p) + values[p - 1 + i]
        return smoothed

    smoothed_tr = _wilder_smooth(true_ranges, period)
    smoothed_plus_dm = _wilder_smooth(plus_dm, period)
    smoothed_minus_dm = _wilder_smooth(minus_dm, period)

    if len(smoothed_tr) == 0 or smoothed_tr[-1] == 0:
        return 0.0, 0.0, 0.0

    di_plus = 100.0 * smoothed_plus_dm / np.where(smoothed_tr == 0, 1e-9, smoothed_tr)
    di_minus = 100.0 * smoothed_minus_dm / np.where(smoothed_tr == 0, 1e-9, smoothed_tr)

    di_sum = di_plus + di_minus
    dx = 100.0 * np.abs(di_plus - di_minus) / np.where(di_sum == 0, 1e-9, di_sum)

    adx_window = dx[-period:] if len(dx) >= period else dx
    adx_value = float(adx_window.mean()) if len(adx_window) else 0.0

    return adx_value, float(di_plus[-1]), float(di_minus[-1])


def _obv_signal(closes: np.ndarray, volumes: np.ndarray, window: int = 20) -> tuple[str, str]:
    """On-Balance Volume (standart, kesin tanımlı: kapanış yukarıysa hacmi
    ekle, aşağıysa çıkar). Ham kümülatif OBV sayısının kendisi zaman
    içinde karşılaştırılabilir değil — burada iki gerçek sinyale
    dönüştürülüyor: (1) OBV'nin kendi son penceredeki trendi, (2) fiyatla
    OBV arasında bir ıraksama (divergence) var mı — fiyat yükselirken
    gerçek hacim akışı (OBV) düşüyorsa bu klasik bir "zayıf rally" uyarısı,
    ve tersi."""
    if len(closes) < 3:
        return "flat", "none"

    obv = np.zeros(len(closes))
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv[i] = obv[i - 1] + volumes[i]
        elif closes[i] < closes[i - 1]:
            obv[i] = obv[i - 1] - volumes[i]
        else:
            obv[i] = obv[i - 1]

    w = min(window, len(closes) - 1)
    obv_change = obv[-1] - obv[-1 - w]
    price_change = closes[-1] - closes[-1 - w]

    obv_trend = "rising" if obv_change > 0 else "falling" if obv_change < 0 else "flat"

    if price_change > 0 and obv_change < 0:
        divergence = "bearish_divergence"  # fiyat yükseliyor, gerçek hacim akışı desteklemiyor
    elif price_change < 0 and obv_change > 0:
        divergence = "bullish_divergence"  # fiyat düşüyor, gerçek hacim akışı desteklemiyor
    else:
        divergence = "none"

    return obv_trend, divergence


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


def _atr(data: list[OHLCV], period: int) -> float:
    """Average True Range — standart, kesin tanımlı volatilite ölçüsü.
    True Range = max(high-low, |high-prev_close|, |low-prev_close|); ATR
    burada basit hareketli ortalama (Wilder'ın üstel düzeltmesi değil,
    daha basit ama eşdeğer bir varyant — açıkça belirtiliyor)."""
    if len(data) < 2 or period < 1:
        return 0.0
    highs = np.array([d.high for d in data], dtype=float)
    lows = np.array([d.low for d in data], dtype=float)
    closes = np.array([d.close for d in data], dtype=float)
    prev_closes = closes[:-1]
    true_ranges = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(np.abs(highs[1:] - prev_closes), np.abs(lows[1:] - prev_closes)),
    )
    window = true_ranges[-period:] if len(true_ranges) >= period else true_ranges
    return float(window.mean()) if len(window) else 0.0


def compute_daily_atr_pct(daily_bars: list[OHLCV], period: int = 14) -> float | None:
    """Faz 251: kritik bulgu — RiskTargetStage stop/target mesafesini
    sinyal zaman diliminin (candle_timeframe, genelde 1m) ATR'sinden
    kuruyordu. 1 dakikalık ATR, kripto gibi yüksek volatiliteli bir
    piyasada bile gürültü seviyesinde kalıyor (gerçek ölçüm: BTCUSDT 1m
    ATR fiyatın sadece ~%0.05'i) — stop, normal bir mumun sıradan
    dalgalanmasından bile küçük kalıp anında tetikleniyordu, yöne hiç
    şans tanımıyordu (kullanıcı bulgusu).

    Kullanıcıyla üzerinde anlaşılan çerçeve: risk ölçeklendirmesi sinyal
    zaman diliminden BAĞIMSIZ, günlük ATR'den (literatürde standart —
    Wilder'ın orijinal ATR tanımı zaten günlük veri için) türetilmeli.
    Bu, hızlı sinyal üretimini (1m) korurken riski gerçekçi, günün gerçek
    volatilitesine göre ölçeklendiriyor — sabit bir yüzde değil, piyasa
    volatilite arttıkça stop de otomatik genişliyor.

    Yüzde olarak dönüyor (mutlak $ değil) — entry_price'a göre ölçek
    bağımsız kalması için (RiskTargetStage bunu güncel fiyatla çarpıyor).
    Yeterli günlük bar yoksa None (fail-closed, icat edilmiş bir sayı
    değil)."""
    if len(daily_bars) < period + 1:
        return None
    atr = _atr(daily_bars, period)
    price = daily_bars[-1].close
    if price <= 0:
        return None
    return atr / price


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
            "fibonacci_nearest_level": "none", "fibonacci_price_position": "none",
            "wyckoff_event": "none",
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
    fib_level, fib_position = _fibonacci_signal(closes, highs, lows, swing_highs, swing_lows)
    wyckoff_event = _wyckoff_event(data)

    return {
        "structure_phase": structure_phase,
        "break_of_structure": break_of_structure,
        "change_of_character": change_of_character,
        "fair_value_gap": fair_value_gap,
        "swing_structure": swing_structure,
        "liquidity_sweep": liquidity_sweep,
        "fibonacci_nearest_level": fib_level,
        "fibonacci_price_position": fib_position,
        "wyckoff_event": wyckoff_event,
    }


def _fibonacci_signal(
    closes: np.ndarray, highs: np.ndarray, lows: np.ndarray,
    swing_highs: list[int], swing_lows: list[int],
) -> tuple[str, str]:
    """Kullanıcı sorusu: "teknik analiz yapıyor mu sistem fibonacci vs?"
    Gerçek bulgu: yapmıyordu — bu proje şimdiye kadar ICT/smart-money
    tarzı yapısal sinyaller (BOS/CHoCH/FVG/likidite süpürme) ve basit
    trend/momentum göstergeleri kullanıyordu, klasik Fibonacci retracement
    hiç yoktu. Standart, kesin tanımlı 23.6/38.2/50/61.8/78.6% seviyeleri
    — en son swing high/low arasında, gerçek yön (tepe->dip mi dip->tepe
    mi son oluştu) baz alınarak hesaplanıyor. Cup&handle gibi şekil-eşleme
    gerektiren desenler kasıtlı olarak eklenmedi — Wyckoff'ta da
    belirtildiği gibi bu projenin dürüstlük ilkesi: öznel/şekil-tanıma
    gerektiren desenleri "hassas tespit" gibi göstermemek. Fibonacci ise
    tam tersine kesin matematiksel bir tanıma sahip, bu yüzden eklendi."""
    if not swing_highs or not swing_lows:
        return "none", "none"

    last_high_idx, last_low_idx = swing_highs[-1], swing_lows[-1]
    swing_high_price, swing_low_price = highs[last_high_idx], lows[last_low_idx]
    price_range = swing_high_price - swing_low_price
    if price_range <= 0:
        return "none", "none"

    # Tepe, dipten SONRA oluştuysa (en son hareket YUKARI) — şimdi tepeden
    # aşağı bir retracement bekleniyor, seviyeler tepeden ölçülür (destek
    # adayları). Tersi durumda (en son hareket AŞAĞI) seviyeler dipten
    # yukarı ölçülür (direnç adayları).
    uptrend = last_high_idx > last_low_idx
    ratios = {"23.6%": 0.236, "38.2%": 0.382, "50.0%": 0.5, "61.8%": 0.618, "78.6%": 0.786}
    current = closes[-1]

    nearest_label, nearest_dist = "none", None
    for label, ratio in ratios.items():
        level_price = (
            swing_high_price - price_range * ratio if uptrend else swing_low_price + price_range * ratio
        )
        dist = abs(current - level_price) / price_range
        if nearest_dist is None or dist < nearest_dist:
            nearest_dist, nearest_label = dist, label

    near_threshold = 0.03  # aralığın %3'ü içindeyse "seviyede" say
    if nearest_dist is not None and nearest_dist < near_threshold:
        position = "at_support" if uptrend else "at_resistance"
    else:
        position = "none"

    return nearest_label, position


def _approximate_wyckoff_phase(data: list[OHLCV]) -> str:
    """Kaba yaklaşım: düşük volatilite + artan hacim + yatay fiyat =
    accumulation-vari; yüksek volatilite + düşen hacim tepe civarında =
    distribution-vari. Gerçek Wyckoff analizi değil, dürüst bir proxy.

    Faz 215: gerçek bulgu — "düşük/yüksek volatilite" sabit bir oranla
    (vol_ratio < 0.8 / > 1.3, son-10-bar / tüm-100-bar) tanımlanıyordu.
    Son 10 bar zaten tüm 100 barın İÇİNDE olduğu için oran neredeyse hep
    1.0 civarında kalıyor, gerçek verilerde (BTC/ETH/SOL) neredeyse hiç
    bu aralığın dışına çıkmıyordu — structure_phase sürekli "neutral"
    çıkıyordu. Codebase'in zaten kullandığı desenle (realized_vol_
    percentile, quant_signals'ta) tutarlı şekilde: mutlak bir oran yerine
    volatilitenin KENDİ yakın geçmişine göre yüzdelik dilimi kullanılıyor
    — kendi kendini normalize ediyor, hangi sembol/zaman dilimi olursa
    olsun anlamlı şekilde tetiklenebiliyor."""
    closes = _closes(data)
    volumes = np.array([d.volume for d in data], dtype=float)
    if len(closes) < 20:
        return "neutral"
    returns = _returns(closes)
    vol_percentile = _realized_vol_percentile(returns)
    volume_trend = volumes[-5:].mean() - volumes[-15:-5].mean() if len(volumes) >= 15 else 0.0
    price_range_pct = (closes[-10:].max() - closes[-10:].min()) / closes[-10:].mean()

    if vol_percentile < 20 and price_range_pct < 0.03 and volume_trend > 0:
        return "accumulation" if closes[-1] < closes[-10:].mean() else "distribution"
    if vol_percentile > 80 and closes[-1] > closes[-10:].mean():
        return "markup"
    if vol_percentile > 80 and closes[-1] < closes[-10:].mean():
        return "markdown"
    return "neutral"


def _wyckoff_event(data: list[OHLCV], window: int = 20) -> str:
    """Faz 237: kullanıcı isteği — "gerçek Wyckoff analizi yaptıralım."
    _approximate_wyckoff_phase() (yukarıda) kasıtlı olarak kaba bir proxy
    olarak kalıyor — genel rejim (accumulation/distribution/markup/
    markdown) hâlâ öznel bir yorum. Ama Wyckoff metodolojisinin KESİN
    TANIMLI, gerçekten ayrık fiyat-hacim olayları var, ve bunlar burada
    gerçekten tespit ediliyor:
    - Spring: fiyat menzil DESTEĞİNİN altına sarkıyor (düşük fitil) ama
      kapanış menzil içine geri dönüyor — klasik "sahte kırılma/shakeout",
      bullish (zayıf elleri temizleyip gerçek alıcıları içeri çekiyor).
    - Upthrust (UT): Spring'in aynası — menzil DİRENCİNİN üstüne sarkıyor,
      kapanış içeri dönüyor, bearish.
    - Sign of Strength (SOS): kapanış menzil direncinin GERÇEKTEN üstünde
      VE hacim kendi yakın geçmiş ortalamasının üstünde — hacimle
      desteklenen gerçek bir kırılım (sadece bir fitil değil).
    - Sign of Weakness (SOW): SOS'un aynası, menzil desteğinin altında.
    Menzil (destek/direnç), ŞU ANKİ bar HARİÇ son `window` bar'ın en düşük
    low'u / en yüksek high'ı — lookahead yok."""
    if len(data) < window + 2:
        return "none"

    highs = np.array([d.high for d in data], dtype=float)
    lows = np.array([d.low for d in data], dtype=float)
    volumes = np.array([d.volume for d in data], dtype=float)

    support = lows[-(window + 1):-1].min()
    resistance = highs[-(window + 1):-1].max()
    avg_volume = volumes[-(window + 1):-1].mean()

    current = data[-1]

    if current.low < support and current.close > support:
        return "spring"
    if current.high > resistance and current.close < resistance:
        return "upthrust"
    if current.close > resistance and current.volume > avg_volume:
        return "sign_of_strength"
    if current.close < support and current.volume > avg_volume:
        return "sign_of_weakness"
    return "none"


def compute_quant_signals(data: list[OHLCV]) -> dict:
    """zscore/realized_vol_percentile/autocorrelation/hurst_exponent —
    hepsi standart, kesin tanımlı istatistiksel hesaplamalar."""
    if len(data) < 20:
        return {
            "zscore": 0.0, "realized_vol_percentile": 50.0, "autocorrelation": 0.0,
            "hurst_exponent": 0.5, "long_term_trend_regime": "insufficient_data",
            "regime_changepoint_detected": False,
        }

    closes = _closes(data)
    returns = _returns(closes)

    window = min(20, len(closes) - 1)
    recent = closes[-window:]
    mean, std = recent.mean(), recent.std()
    zscore = (closes[-1] - mean) / std if std > 0 else 0.0

    realized_vol_percentile = _realized_vol_percentile(returns)
    autocorrelation = _autocorrelation(returns)
    hurst_exponent = _hurst_exponent(closes)
    long_term_trend_regime = _long_term_trend_regime(closes)
    regime_changepoint_detected = _regime_changepoint(returns)

    return {
        "zscore": round(float(zscore), 3),
        "realized_vol_percentile": round(float(realized_vol_percentile), 1),
        "autocorrelation": round(float(autocorrelation), 3),
        "hurst_exponent": round(float(hurst_exponent), 3),
        "long_term_trend_regime": long_term_trend_regime,
        "regime_changepoint_detected": regime_changepoint_detected,
    }


def _long_term_trend_regime(closes: np.ndarray) -> str:
    """Faz 222: kullanıcı bulgusu — "geçmiş pencere 20-1000 arası çok
    yetersiz." Araştırınca gerçek bulgu şuydu: mevcut hiçbir gösterge
    50 bardan fazlasını kullanmıyordu (compute_technical_signals'daki
    "ema200" bile aslında min(50, n-1) periyotlu, gerçek bir 200 EMA
    değildi) — yani 1000'e kadar olan derin geçmişin canlı sinyallere
    hiçbir katkısı yoktu. candle_lookback artık pagination ile 1000'in
    üzerine çıkabiliyor (BinanceAdapter.fetch_ohlcv) — bu, o derin
    geçmişi GERÇEKTEN kullanan ilk gösterge: gerçek (yaklaştırma değil)
    200-periyotluk EMA + son 20 barlık eğimi.

    En az 220 bar (200 EMA'nın anlamlı yakınsaması için tampon) ister —
    yetersizse kısa bir pencereyle sahte bir "200 EMA" gibi davranmak
    yerine dürüstçe "insufficient_data" döner."""
    n = len(closes)
    if n < 220:
        return "insufficient_data"
    ema200 = _ema_series(closes, 200)
    current_price = closes[-1]
    current_ema = ema200[-1]
    slope = ema200[-1] - ema200[-20]
    if current_price > current_ema and slope > 0:
        return "bull_trend"
    if current_price < current_ema and slope < 0:
        return "bear_trend"
    return "transition"


def _regime_changepoint(returns: np.ndarray, window: int = 20, significance_level: float = 0.05) -> bool:
    """Faz 268-sonrası — gerçek olay (2026-08-12): long_term_trend_regime
    (200-EMA tabanlı, YAVAŞ/gecikmeli) fiyat aktif olarak tersine
    dönerken bile eski rejimi okumaya devam edip 50 ardışık gerçek
    kayba katkıda bulundu (agents/quant_agent.py'nin döküman notuna
    bkz.). Bu, icat edilmiş bir "rejim" modeli (HMM vb.) DEĞİL — son
    `window` barın ortalama getirisini, ondan önceki `window` barınkiyle
    Welch's t-test'iyle (services/ab_testing.py'nin zaten kullandığı AYNI
    araç) karşılaştıran basit, açıklanabilir bir iki-örneklem testi.
    Sadece YÖN DEĞİŞTİYSE (işaret farklıysa) True — aynı yönde
    hızlanma/yavaşlama bir "changepoint" sayılmıyor, asıl ilgilenilen
    risk yönün tersine dönmesi."""
    if len(returns) < 2 * window:
        return False

    recent = returns[-window:]
    prior = returns[-2 * window:-window]
    recent_mean, prior_mean = float(recent.mean()), float(prior.mean())
    if recent_mean == 0 or np.sign(recent_mean) == np.sign(prior_mean):
        return False
    if recent.std() == 0 and prior.std() == 0:
        return False

    from scipy import stats
    try:
        result = stats.ttest_ind(recent, prior, equal_var=False)
    except Exception:
        return False
    p_value = float(result.pvalue)
    if np.isnan(p_value):
        return False

    return p_value < significance_level


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
    """Varyans-ölçekleme (generalized Hurst) yöntemiyle basit Hurst
    tahmini. Standart, literatürde tanımlı bir yöntem — ama küçük
    örneklemlerde gürültülü olduğu bilinen, kabaca bir tahmin (gerçek
    zaman serisi analizi bu konuda çok daha büyük örneklemler ister).

    Faz 214: gerçek bulgu — burası log(closes) yerine log_returns'ün
    kendisini (yani fiyatın değil, GETİRİNİN) lag'lenmiş farkını
    kullanıyordu. Getiriler zaten ~durağan/beyaz gürültüye yakın
    olduğundan, bu fark hemen her lag'de neredeyse sabit çıkıyor —
    regresyon eğimi (ve dolayısıyla Hurst) piyasa rejiminden bağımsız
    olarak sürekli ~0'a çöküyordu (canlı BTCUSDT verisiyle doğrulandı:
    hurst=0.0, düzeltmeden sonra aynı veriyle hurst=0.31). Bu da
    QuantAgent'ın neredeyse her zaman "mean_reverting_regime" (hurst<0.45
    her zaman trivially doğru) sanıp aşırı z-score beklemesine, yani
    fiilen hep WAIT/0 confidence üretmesine sebep oluyordu. Doğru yöntem
    fiyatın (log) kendisinin lag'lenmiş farkının varyansını ölçeklemek."""
    n = len(closes)
    if n < 20:
        return 0.5
    log_prices = np.log(closes)
    lags = [l for l in (5, 10, 20, 40) if l < len(log_prices)]
    if len(lags) < 2:
        return 0.5

    tau = []
    for lag in lags:
        diffs = log_prices[lag:] - log_prices[:-lag]
        tau.append(np.sqrt(np.std(diffs)) if np.std(diffs) > 0 else 1e-9)

    try:
        poly = np.polyfit(np.log(lags), np.log(tau), 1)
        hurst = poly[0] * 2.0
    except (np.linalg.LinAlgError, ValueError):
        return 0.5

    if math.isnan(hurst) or math.isinf(hurst):
        return 0.5
    return float(np.clip(hurst, 0.0, 1.0))


# Faz 268-sonrası: Data Quality Scoring — fiyat spike/wick manipülasyonu
# tespiti. Bir fitilin "gerçek" (ör. gerçek bir flash crash) mi yoksa
# "kötü print" (borsa/veri sağlayıcı hatası, tek bir anormal trade) mi
# olduğunu ayırt eden klasik işaret: gerçek bir hareketin bir miktar
# devamı olur, kötü bir print BİR SONRAKİ bar'da neredeyse tamamen
# tersine döner (fiyat sanki hiç oraya gitmemiş gibi geri gelir).
_WICK_BODY_RATIO_THRESHOLD = 4.0
_WICK_RANGE_FRACTION_THRESHOLD = 0.6
_REVERSION_FRACTION_THRESHOLD = 0.3


def compute_data_quality_score(data: list[OHLCV]) -> dict:
    """OHLC iç tutarlılığı (high<low, open/close aralık dışı, negatif
    hacim gibi kesin hatalar) VE aşırı fitil + hemen sonraki bar'da tam
    tersine dönüş (kötü print şüphesi, aşağıdaki modül notuna bkz.)
    kontrol ediyor. data_quality_score = 1.0 - (anomali sayısı / bar
    sayısı) — 1.0 tamamen temiz, düşük değer şüpheli veri oranı yüksek
    demek. <5 bar'da (istatistiksel olarak anlamsız) dürüstçe temiz
    varsayılıyor (fail-open — icat edilmiş bir şüphe uydurulmaz)."""
    if len(data) < 5:
        return {"data_quality_score": 1.0, "anomaly_count": 0, "anomalies": []}

    anomalies: list[str] = []
    for i, bar in enumerate(data):
        # 1. OHLC iç tutarlılığı — kesin, tartışmasız hatalar.
        if bar.high < bar.low:
            anomalies.append(f"bar {i}: high < low")
            continue
        if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
            anomalies.append(f"bar {i}: open/close, high-low aralığının dışında")
            continue
        if bar.volume < 0:
            anomalies.append(f"bar {i}: negatif hacim")

        # 2. Aşırı fitil + hemen sonraki bar'da tam tersine dönüş.
        full_range = bar.high - bar.low
        if full_range <= 0:
            continue
        body = abs(bar.close - bar.open)
        upper_wick = bar.high - max(bar.open, bar.close)
        lower_wick = min(bar.open, bar.close) - bar.low
        max_wick = max(upper_wick, lower_wick)
        if body <= 0 or max_wick <= _WICK_BODY_RATIO_THRESHOLD * body:
            continue
        if max_wick <= full_range * _WICK_RANGE_FRACTION_THRESHOLD:
            continue
        if i + 1 >= len(data):
            continue
        extreme_price = bar.high if upper_wick > lower_wick else bar.low
        next_close = data[i + 1].close
        wick_excursion = abs(extreme_price - bar.close)
        if wick_excursion <= 0:
            continue
        reverted = abs(next_close - bar.close) < wick_excursion * _REVERSION_FRACTION_THRESHOLD
        if reverted:
            anomalies.append(
                f"bar {i}: aşırı fitil (gövdenin {max_wick / body:.1f}x'i), "
                "bir sonraki bar'da neredeyse tam tersine dönüyor — kötü print şüphesi"
            )

    score = max(0.0, 1.0 - len(anomalies) / len(data))
    return {
        "data_quality_score": round(score, 4),
        "anomaly_count": len(anomalies),
        "anomalies": anomalies[:20],
    }
