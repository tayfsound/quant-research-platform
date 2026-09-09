"""Faz 461 — market_data/features/order_flow_pressure.py birim testleri.

Ayrıca `_parse_klines()`'ın artık atılan alanları koruduğunu GERÇEK
Binance cevabıyla doğruluyor (proje disiplini: yeni bir dış-veri
entegrasyonu gerçek veriyle sınanır -- Faz 440'ın premiumIndex testiyle
AYNI desen).
"""
import math

from market_data.features.order_flow_pressure import (
    compute_order_flow_pressure,
    compute_taker_buy_ratios,
)


def _candles(ratios, volume=100.0):
    return [
        {"volume": volume, "taker_buy_base": None if r is None else r * volume}
        for r in ratios
    ]


def test_taker_buy_ratio_basic():
    candles = _candles([0.5, 0.75, 0.25])
    assert compute_taker_buy_ratios(candles) == [0.5, 0.75, 0.25]


def test_taker_buy_ratio_fails_closed_on_missing_or_degenerate_data():
    """Faz 461 ÖNCESİ kaydedilmiş mumlarda bu alan NULL -- uydurma bir
    oran (ör. 0.5) üretmek modele yanlış bilgi öğretirdi."""
    assert compute_taker_buy_ratios([{"volume": 100.0, "taker_buy_base": None}]) == [None]
    assert compute_taker_buy_ratios([{"volume": 0.0, "taker_buy_base": 5.0}]) == [None]
    assert compute_taker_buy_ratios([{"volume": 100.0}]) == [None]


def test_taker_buy_ratio_rejects_out_of_range_values():
    """Oran tanımı gereği [0,1]; dışına çıkan değer bozuk veridir --
    kırpılmaz, ELENİR (kırpmak bozuk veriyi meşru gösterirdi)."""
    assert compute_taker_buy_ratios([{"volume": 100.0, "taker_buy_base": 150.0}]) == [None]
    assert compute_taker_buy_ratios([{"volume": 100.0, "taker_buy_base": -5.0}]) == [None]


def test_pressure_zscore_uses_standard_error_not_raw_sd():
    """BİR ÖLÇÜM HATASINDAN ÖĞRENİLDİ: pencere ORTALAMASI, tek tek
    mumlardan ~sqrt(n) kat dar dağılır. İlk denemede ortalama, tek-mum
    standart sapmasına bölündüğü için 33.750 gözlemin sadece 39'u |z|>=1
    çıkmış ve sinyal görünmez olmuştu.

    Burada 15 mumluk pencere, taban ortalamasından tam 1 ham standart
    sapma yukarıda; doğru payda (sd/sqrt(15)) kullanılırsa z ≈ sqrt(15)
    ≈ 3,87 olmalı, ham sd kullanılsaydı 1,0 çıkardı."""
    import random

    rng = random.Random(5)
    baseline = [rng.gauss(0.50, 0.05) for _ in range(120)]
    baseline = [min(0.99, max(0.01, b)) for b in baseline]
    import statistics
    sd = statistics.pstdev(baseline)
    mean = statistics.mean(baseline)
    recent = [mean + sd] * 15

    result = compute_order_flow_pressure(_candles(baseline + recent))

    assert result is not None
    assert math.isclose(result["pressure_zscore"], math.sqrt(15), rel_tol=0.05)


def test_extreme_buying_and_selling_states():
    baseline = [0.50] * 120
    # pstdev=0 -> fail-closed; kucuk bir varyans ekleyelim.
    baseline = [0.50 + (0.01 if i % 2 else -0.01) for i in range(120)]

    yuksek = compute_order_flow_pressure(_candles(baseline + [0.60] * 15))
    dusuk = compute_order_flow_pressure(_candles(baseline + [0.40] * 15))

    assert yuksek["pressure_state"] == "extreme_buying"
    assert yuksek["pressure_zscore"] > 2.0
    assert dusuk["pressure_state"] == "extreme_selling"
    assert dusuk["pressure_zscore"] < -2.0


def test_neutral_when_recent_matches_baseline():
    baseline = [0.50 + (0.01 if i % 2 else -0.01) for i in range(120)]
    result = compute_order_flow_pressure(_candles(baseline + [0.50] * 15))
    assert result["pressure_state"] == "neutral"
    assert abs(result["pressure_zscore"]) < 0.75


def test_fails_closed_without_enough_history():
    baseline = [0.50 + (0.01 if i % 2 else -0.01) for i in range(50)]
    assert compute_order_flow_pressure(_candles(baseline)) is None


def test_fails_closed_when_history_is_mostly_null():
    """Faz 461 öncesi mumlar NULL taşıyor; kapsama yarının altındaysa
    hesaplanan taban güvenilir değil."""
    baseline = [None] * 100 + [0.5 + (0.01 if i % 2 else -0.01) for i in range(20)]
    assert compute_order_flow_pressure(_candles(baseline + [0.60] * 15)) is None


def test_fails_closed_on_zero_variance_baseline():
    """Tabanın varyansı sıfırsa z-skor tanımsız -- sonsuz/uydurma bir
    sayı yerine None."""
    assert compute_order_flow_pressure(_candles([0.50] * 120 + [0.60] * 15)) is None


def test_parse_klines_keeps_the_previously_discarded_fields():
    """GERÇEK Binance cevabı üzerinde: Faz 461 öncesi bu dört alan
    atılıyordu. Regresyon koruması -- biri geri düşerse test kırılır."""
    import httpx

    from exchange_gateway.binance.adapter import BinanceAdapter

    resp = httpx.get(
        "https://api.binance.com/api/v3/klines",
        params={"symbol": "BTCUSDT", "interval": "1m", "limit": 3}, timeout=20,
    )
    resp.raise_for_status()
    bars = BinanceAdapter._parse_klines(resp.json())

    assert len(bars) == 3
    for bar in bars:
        # Eski alanlar BIREBIR duruyor (regresyon yok).
        assert bar["close"] > 0 and bar["volume"] >= 0
        # Yeni alanlar GERCEKTEN geliyor.
        assert bar["quote_volume"] is not None and bar["quote_volume"] > 0
        assert bar["trades"] is not None and bar["trades"] >= 0
        assert bar["taker_buy_base"] is not None
        # Agresif alis hacmi toplam hacmi asamaz.
        assert 0 <= bar["taker_buy_base"] <= bar["volume"] + 1e-9


def test_pressure_on_real_binance_data():
    """Uçtan uca gerçek veri: canlı mumlardan gerçek bir baskı z-skoru
    üretilebiliyor mu (sentetik fikstürde gizlenen alan adı/ölçek
    hataları burada yakalanır)."""
    import httpx

    from exchange_gateway.binance.adapter import BinanceAdapter

    resp = httpx.get(
        "https://api.binance.com/api/v3/klines",
        params={"symbol": "BTCUSDT", "interval": "1m", "limit": 200}, timeout=20,
    )
    resp.raise_for_status()
    result = compute_order_flow_pressure(BinanceAdapter._parse_klines(resp.json()))

    assert result is not None
    assert 0.0 <= result["taker_buy_ratio"] <= 1.0
    assert result["pressure_state"] in (
        "extreme_buying", "buying", "neutral", "selling", "extreme_selling",
    )
    assert math.isfinite(result["pressure_zscore"])
