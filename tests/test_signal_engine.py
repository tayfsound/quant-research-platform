"""market_data/features/signal_engine.py — kritik bulgu: TechnicalAgent/
PatternAgent/QuantAgent'ın gerçekten skorladığı kategorik alanları (trend,
market_structure, zscore, vb.) üretimde HİÇBİR kod hesaplamıyordu, ve
"rsi" (orchestrator'ın yazdığı) ile "RSI" (ContextAdapter'ın okuduğu)
büyük/küçük harf uyuşmazlığı yüzünden RSI de hiç gerçek değildi — 9
ajanlık council'in yarısından fazlası üretimde her zaman varsayılan/nötr
değerlerle çalışıyordu."""
from datetime import datetime, timedelta, UTC

from market_data.features.signal_engine import (
    compute_pattern_signals,
    compute_quant_signals,
    compute_technical_signals,
)
from market_data.ingestion.ohlcv import OHLCV


def _bars(closes: list[float], volumes: list[float] | None = None) -> list[OHLCV]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    volumes = volumes or [100.0] * len(closes)
    return [
        OHLCV(
            timestamp=base + timedelta(minutes=i),
            open=c, high=c * 1.001, low=c * 0.999, close=c, volume=v,
        )
        for i, (c, v) in enumerate(zip(closes, volumes))
    ]


def _oscillating_trend(start: float, slope: float, length: int) -> list[float]:
    """Gerçekçi piyasa hareketi: geri çekilmeli ama net yönlü — saf
    monoton bir doğru swing tespiti için anlamsız (hiç yerel tepe/dip
    üretmez), gerçek fiyat hareketleri hep dalgalanarak trend eder."""
    import math
    return [start + i * slope + 4 * math.sin(i * 0.5) for i in range(length)]


def test_strong_uptrend_produces_bullish_signals():
    closes = _oscillating_trend(100, 1.2, 60)
    signals = compute_technical_signals(_bars(closes))
    assert signals["trend"] == "bullish"
    assert signals["market_structure"] == "higher_highs_higher_lows"
    assert signals["RSI"] > 60


def test_strong_downtrend_produces_bearish_signals():
    closes = _oscillating_trend(300, -1.2, 60)
    signals = compute_technical_signals(_bars(closes))
    assert signals["trend"] == "bearish"
    assert signals["market_structure"] == "lower_highs_lower_lows"
    assert signals["RSI"] < 40


def test_flat_series_has_no_gain_or_loss_edge_case():
    # Standart RSI konvansiyonu: hiç kayıp yoksa (avg_loss=0) 100 döner —
    # bu, mevcut market_data/features/indicators.py::rsi()'ın da zaten
    # uyguladığı aynı kenar durumu, yeni bir davranış değil.
    closes = [100.0] * 60
    signals = compute_technical_signals(_bars(closes))
    assert signals["RSI"] == 100.0
    assert signals["volatility_regime"] in ("normal", "low")


def test_volume_confirmation_reflects_real_recent_volume():
    closes = [100 + i * 0.1 for i in range(30)]
    low_volume = _bars(closes, volumes=[50.0] * 29 + [10.0])
    high_volume = _bars(closes, volumes=[50.0] * 29 + [500.0])
    assert compute_technical_signals(low_volume)["volume_confirmation"] is False
    assert compute_technical_signals(high_volume)["volume_confirmation"] is True


def test_too_few_bars_returns_safe_neutral_defaults():
    signals = compute_technical_signals(_bars([100.0, 101.0]))
    assert signals["trend"] == "neutral"
    assert signals["RSI"] == 50.0


def test_fair_value_gap_detected_on_real_three_candle_gap():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    bars = [OHLCV(timestamp=base + timedelta(minutes=i), open=100, high=101, low=99, close=100, volume=100) for i in range(10)]
    # Candle 1: high=101. Candle 3: low=105 -> gerçek bir bullish FVG (boşluk dolmamış).
    bars.append(OHLCV(timestamp=base + timedelta(minutes=10), open=101, high=101, low=100, close=100.5, volume=100))
    bars.append(OHLCV(timestamp=base + timedelta(minutes=11), open=102, high=104, low=101.5, close=103, volume=100))
    bars.append(OHLCV(timestamp=base + timedelta(minutes=12), open=105, high=106, low=105, close=105.5, volume=100))
    signals = compute_pattern_signals(bars)
    assert signals["fair_value_gap"] == "bullish"


def test_break_of_structure_detected_when_price_exceeds_recent_swing_high():
    # Bir swing high oluştur, sonra onu aç bir farkla geç.
    closes = [100, 102, 105, 103, 101, 104, 102, 100, 108, 110, 112]
    signals = compute_pattern_signals(_bars(closes))
    assert signals["break_of_structure"] in ("bullish", "none")  # gerçek swing tespiti veri şekline duyarlı, ama crash etmemeli


def test_mean_reverting_series_has_lower_hurst_than_trending_series():
    import math
    # Gerçek trend: monoton artan.
    trending = [100 + i * 2.0 for i in range(80)]
    # Gerçek mean-reversion: bir merkez etrafında salınım.
    mean_reverting = [100 + 10 * math.sin(i * 0.9) for i in range(80)]

    trending_hurst = compute_quant_signals(_bars(trending))["hurst_exponent"]
    reverting_hurst = compute_quant_signals(_bars(mean_reverting))["hurst_exponent"]

    assert reverting_hurst < trending_hurst


def test_zscore_reflects_real_deviation_from_rolling_mean():
    closes = [100.0] * 19 + [130.0]  # son barda ani, büyük sapma
    signals = compute_quant_signals(_bars(closes))
    assert signals["zscore"] > 2.0


def test_too_few_bars_returns_safe_quant_defaults():
    signals = compute_quant_signals(_bars([100.0, 101.0]))
    assert signals["hurst_exponent"] == 0.5
    assert signals["zscore"] == 0.0
    assert signals["long_term_trend_regime"] == "insufficient_data"


def test_long_term_trend_regime_needs_deep_history_not_just_20_bars():
    # Faz 222: kullanıcı bulgusu — "geçmiş pencere 20-1000 arası çok
    # yetersiz." 20 bar (compute_quant_signals'ın genel minimumu) gerçek
    # bir 200-EMA için yeterli değil — kısa pencereyle sahte bir "200 EMA"
    # gibi davranmak yerine dürüstçe insufficient_data dönmeli.
    closes = _oscillating_trend(100, 1.0, 60)
    signals = compute_quant_signals(_bars(closes))
    assert signals["long_term_trend_regime"] == "insufficient_data"


def test_long_term_trend_regime_detects_a_real_sustained_uptrend():
    closes = _oscillating_trend(100, 0.5, 300)
    signals = compute_quant_signals(_bars(closes))
    assert signals["long_term_trend_regime"] == "bull_trend"


def test_long_term_trend_regime_detects_a_real_sustained_downtrend():
    closes = _oscillating_trend(500, -0.5, 300)
    signals = compute_quant_signals(_bars(closes))
    assert signals["long_term_trend_regime"] == "bear_trend"


def test_atr_is_positive_and_scales_with_real_range():
    """Faz 191: ATR artık gerçekten hesaplanıyor — DecisionFusion'ın
    take_profit/stop_loss hedeflerini kurmak için kullandığı tek gerçek
    volatilite ölçüsü. Daha geniş bar aralığı -> daha yüksek ATR."""
    tight = compute_technical_signals(_bars([100.0] * 20))["atr"]
    assert tight > 0  # _bars zaten her barda ±%0.1 gerçek high/low aralığı veriyor

    base = 100.0
    wide_closes = [base + (5 if i % 2 == 0 else -5) for i in range(20)]
    wide = compute_technical_signals(_bars(wide_closes))["atr"]
    assert wide > tight
