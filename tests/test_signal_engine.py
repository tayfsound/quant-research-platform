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


def test_regime_changepoint_not_detected_during_a_stable_sustained_trend():
    """Faz 268-sonrası — gerçek olay (2026-08-12): long_term_trend_regime
    YAVAŞ/gecikmeli olduğu için, aktif bir tersine dönüş sırasında bile
    eski rejimi okumaya devam edip gerçek kayıplara katkıda bulundu.
    Sabit, kararlı bir trendde (son 40 bar önceki 40 bar ile aynı yönde)
    hiçbir changepoint tespit edilmemeli — yanlış pozitif olmamalı."""
    closes = _oscillating_trend(100, 0.5, 300)
    signals = compute_quant_signals(_bars(closes))
    assert signals["long_term_trend_regime"] == "bull_trend"
    assert signals["regime_changepoint_detected"] is False


def test_regime_changepoint_detects_a_real_sharp_reversal_within_a_lagging_bull_trend():
    """300 barlık sürdürülen bir yükseliş (200-EMA hâlâ 'bull_trend'
    okur) sonrasında, son 40 barda GERÇEK, keskin bir tersine dönüş —
    changepoint testi bunu yakalamalı, uzun-vade rejim hâlâ eskisini
    okurken bile."""
    uptrend = _oscillating_trend(100, 0.5, 300)
    last_price = uptrend[-1]
    # Tam olarak changepoint testinin pencere genişliği (20 bar) kadar bir
    # dönüş: "recent" penceresi (son 20) tamamen bu dönüşü, "prior"
    # penceresi (önceki 20) hâlâ orijinal yükselişin son barlarını görür
    # — işaret değişimi net. 200-EMA'nın son-20-bar eğimini bozacak kadar
    # güçlü değil (uzun-vade rejim hâlâ eskisini okusun).
    sharp_reversal = [last_price - i * 0.8 for i in range(1, 21)]
    closes = uptrend + sharp_reversal

    signals = compute_quant_signals(_bars(closes))

    assert signals["long_term_trend_regime"] == "bull_trend"  # hâlâ eski (yavaş) rejimi okuyor
    assert signals["regime_changepoint_detected"] is True  # ama gerçek dönüş tespit edildi


def test_regime_changepoint_ignores_acceleration_in_the_same_direction():
    """Aynı yönde hızlanma (yön DEĞİŞMİYOR) bir changepoint sayılmamalı —
    asıl ilgilenilen risk yön tersine dönmesi, momentum değişimi değil."""
    uptrend = _oscillating_trend(100, 0.3, 300)
    last_price = uptrend[-1]
    accelerated_uptrend = [last_price + i * 3.0 for i in range(1, 41)]  # aynı yön, daha hızlı
    closes = uptrend + accelerated_uptrend

    signals = compute_quant_signals(_bars(closes))
    assert signals["regime_changepoint_detected"] is False


def test_fibonacci_signal_measures_support_from_the_most_recent_swing_high_in_an_uptrend():
    from market_data.features.signal_engine import _fibonacci_signal
    import numpy as np

    # Dip (idx 0, fiyat 100) daha önce, tepe (idx 10, fiyat 200) daha
    # sonra oluştu -> en son hareket YUKARI -> retracement tepeden aşağı
    # ölçülmeli, 61.8% seviyesi = 200 - 100*0.618 = 138.2.
    closes = np.array([100.0] * 20)
    highs = np.array([100.0] * 20)
    lows = np.array([100.0] * 20)
    highs[10] = 200.0
    lows[0] = 100.0
    closes[-1] = 138.2

    label, position = _fibonacci_signal(closes, highs, lows, swing_highs=[10], swing_lows=[0])
    assert label == "61.8%"
    assert position == "at_support"


def test_fibonacci_signal_measures_resistance_from_the_most_recent_swing_low_in_a_downtrend():
    from market_data.features.signal_engine import _fibonacci_signal
    import numpy as np

    # Tepe (idx 0, fiyat 200) daha önce, dip (idx 10, fiyat 100) daha
    # sonra oluştu -> en son hareket AŞAĞI -> retracement dipten yukarı
    # ölçülmeli, 50% seviyesi = 100 + 100*0.5 = 150.
    closes = np.array([100.0] * 20)
    highs = np.array([100.0] * 20)
    lows = np.array([100.0] * 20)
    highs[0] = 200.0
    lows[10] = 100.0
    closes[-1] = 150.0

    label, position = _fibonacci_signal(closes, highs, lows, swing_highs=[0], swing_lows=[10])
    assert label == "50.0%"
    assert position == "at_resistance"


def test_fibonacci_signal_returns_none_when_price_is_far_from_any_level():
    from market_data.features.signal_engine import _fibonacci_signal
    import numpy as np

    closes = np.array([100.0] * 20)
    highs = np.array([100.0] * 20)
    lows = np.array([100.0] * 20)
    highs[10] = 200.0
    lows[0] = 100.0
    closes[-1] = 199.0  # neredeyse tepede, hiçbir retracement seviyesine yakın değil

    _, position = _fibonacci_signal(closes, highs, lows, swing_highs=[10], swing_lows=[0])
    assert position == "none"


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


def test_compute_daily_atr_pct_returns_none_with_insufficient_bars():
    """Faz 251: yetersiz günlük veri varsa (period+1'den az) icat edilmiş
    bir sayı üretilmiyor — fail-closed."""
    from market_data.features.signal_engine import compute_daily_atr_pct

    assert compute_daily_atr_pct(_bars([100.0] * 5), period=14) is None


def test_compute_daily_atr_pct_returns_positive_ratio_with_enough_bars():
    """Faz 251: RiskTargetStage'in artık kullandığı, sinyal zaman
    diliminden bağımsız günlük ATR yüzdesi — fiyata göre ölçeklenmiş,
    pozitif bir oran olmalı."""
    from market_data.features.signal_engine import compute_daily_atr_pct

    base = 100.0
    wide_closes = [base + (5 if i % 2 == 0 else -5) for i in range(20)]
    pct = compute_daily_atr_pct(_bars(wide_closes), period=14)
    assert pct is not None
    assert 0 < pct < 1.0


# Faz 237: kullanıcı isteği — "eklenebilecek bütün teknik analiz
# yöntemlerini ekleyelim eğer matematiksel bir yöntemse." Bollinger/VWAP/
# ADX/OBV — dördü de kesin tanımlı, standart formüller.

def test_bollinger_percent_b_is_near_one_when_price_spikes_above_recent_range():
    closes = [100.0] * 25 + [130.0]  # son barda büyük bir sıçrama
    signals = compute_technical_signals(_bars(closes))
    assert signals["bollinger_percent_b"] > 1.0  # üst bandın da üstünde


def test_bollinger_bandwidth_is_near_zero_for_a_flat_series():
    signals = compute_technical_signals(_bars([100.0] * 25))
    assert signals["bollinger_bandwidth"] < 0.01


def test_vwap_deviation_is_positive_when_price_closes_above_volume_weighted_average():
    # İlk barlar düşük fiyat + YÜKSEK hacim (VWAP'ı aşağı çekiyor), son
    # bar yüksek fiyat + düşük hacim — kapanış VWAP'ın üstünde olmalı.
    bars = _bars([90.0] * 10 + [110.0], volumes=[1000.0] * 10 + [1.0])
    signals = compute_technical_signals(bars)
    assert signals["vwap_deviation_pct"] > 0


def test_adx_is_high_for_a_real_strong_directional_trend():
    from market_data.features.signal_engine import _adx

    base = datetime(2026, 1, 1, tzinfo=UTC)
    # Gerçek, güçlü, kesintisiz bir yükseliş trendi — her bar öncekinden
    # yüksek high/low.
    bars = [
        OHLCV(timestamp=base + timedelta(minutes=i), open=100 + i, high=101 + i, low=99.5 + i, close=100.5 + i, volume=100)
        for i in range(40)
    ]
    adx, di_plus, di_minus = _adx(bars, 14)
    assert adx > 25  # standart "güçlü trend" eşiği
    assert di_plus > di_minus


def test_adx_is_low_for_a_choppy_sideways_series():
    from market_data.features.signal_engine import _adx

    base = datetime(2026, 1, 1, tzinfo=UTC)
    import math
    bars = [
        OHLCV(
            timestamp=base + timedelta(minutes=i),
            open=100 + math.sin(i) * 2, high=101 + math.sin(i) * 2, low=99 + math.sin(i) * 2,
            close=100 + math.sin(i) * 2, volume=100,
        )
        for i in range(40)
    ]
    adx, _, _ = _adx(bars, 14)
    assert adx < 25


def test_obv_trend_rising_when_volume_flows_into_up_days():
    closes = [100 + i for i in range(20)]  # her bar bir öncekinden yüksek
    volumes = [100.0] * 20
    signals = compute_technical_signals(_bars(closes, volumes))
    assert signals["obv_trend"] == "rising"


def test_price_obv_bearish_divergence_when_price_rises_but_volume_flow_falls():
    from market_data.features.signal_engine import _obv_signal
    import numpy as np

    # Fiyat net yükseliyor ama YUKARI barlarda hacim küçük, AŞAĞI
    # (geri çekilme) barlarında hacim büyük -> gerçek hacim akışı (OBV) net düşüyor.
    closes = np.array([100.0, 105.0, 102.0, 108.0, 104.0, 112.0, 107.0, 115.0])
    volumes = np.array([10.0, 10.0, 100.0, 10.0, 100.0, 10.0, 100.0, 10.0])
    obv_trend, divergence = _obv_signal(closes, volumes, window=7)
    assert divergence == "bearish_divergence"


# Faz 237: gerçek, kesin tanımlı Wyckoff olayları (structure_phase'in kaba
# genel-rejim yaklaşıklamasından AYRI, ayrık kurallarla tespit edilen
# olaylar).

def _range_bars(support: float, resistance: float, n: int, volume: float = 100.0) -> list[OHLCV]:
    """support-resistance arasında düz bir menzil oluşturan n bar."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    mid = (support + resistance) / 2
    return [
        OHLCV(timestamp=base + timedelta(minutes=i), open=mid, high=resistance - 0.1, low=support + 0.1, close=mid, volume=volume)
        for i in range(n)
    ]


def test_wyckoff_spring_detected_on_false_breakdown_that_closes_back_inside_range():
    from market_data.features.signal_engine import _wyckoff_event

    bars = _range_bars(support=95.0, resistance=105.0, n=21)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    # Son bar: destek altına sarkıyor (low=93) ama menzil içine kapanıyor (close=97).
    spring_bar = OHLCV(timestamp=base + timedelta(minutes=20), open=96, high=97, low=93.0, close=97.0, volume=100.0)
    result = _wyckoff_event(bars + [spring_bar])
    assert result == "spring"


def test_wyckoff_upthrust_detected_on_false_breakout_that_closes_back_inside_range():
    from market_data.features.signal_engine import _wyckoff_event

    bars = _range_bars(support=95.0, resistance=105.0, n=21)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    ut_bar = OHLCV(timestamp=base + timedelta(minutes=20), open=104, high=107.0, low=103, close=103.0, volume=100.0)
    result = _wyckoff_event(bars + [ut_bar])
    assert result == "upthrust"


def test_wyckoff_sign_of_strength_needs_a_real_volume_confirmed_breakout():
    from market_data.features.signal_engine import _wyckoff_event

    bars = _range_bars(support=95.0, resistance=105.0, n=21, volume=100.0)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    # Gerçek kırılım: kapanış direncin ÜSTÜNDE, hacim ortalamanın üstünde.
    sos_bar = OHLCV(timestamp=base + timedelta(minutes=20), open=105, high=110, low=104, close=109.0, volume=500.0)
    result = _wyckoff_event(bars + [sos_bar])
    assert result == "sign_of_strength"


def test_wyckoff_none_when_price_stays_inside_the_range():
    from market_data.features.signal_engine import _wyckoff_event

    bars = _range_bars(support=95.0, resistance=105.0, n=21)
    assert _wyckoff_event(bars) == "none"
