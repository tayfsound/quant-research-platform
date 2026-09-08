"""Faz 407 — kullanıcı isteği: "ölçtüğümüz her veri için zaman içindeki
stabilitesini de ölçelim." historical_analog_gatherer.py'nin her
kovaya (domains+market_regime+direction+reversing) geçmiş snapshot'lardan
win_rate_stability eklediğini doğruluyor — SADECE gözlem, hiçbir kova
filtrelenmiyor/reddedilmiyor."""
from services.historical_analog_gatherer import _analog_key, _attach_win_rate_stability


def _analog(
    domains, regime, direction, reversing, win_rate,
    volatility_regime="normal", structure_phase="neutral", trade_type="scalp",
):
    return {
        "domains": domains, "market_regime": regime, "direction": direction,
        "reversing": reversing, "win_rate": win_rate,
        # Faz 450 — 7 boyutlu genişletme: _analog_key() artık bu üç alanı
        # da anahtara katıyor.
        "volatility_regime": volatility_regime, "structure_phase": structure_phase, "trade_type": trade_type,
    }


def test_attaches_none_when_no_past_snapshots_exist():
    """Fail-closed: hiç geçmiş yoksa (ilk çalıştırma) stabilite hesaplanamaz."""
    analogs = [_analog(["macro", "technical"], "bull_trend", "LONG", False, 0.75)]
    _attach_win_rate_stability(analogs, past_snapshots=[])
    assert analogs[0]["win_rate_stability"] is None


def test_attaches_real_stability_from_matching_past_snapshots():
    analogs = [_analog(["macro", "technical"], "bull_trend", "LONG", False, 0.80)]
    past_snapshots = [
        {"result": {"analogs": [_analog(["macro", "technical"], "bull_trend", "LONG", False, 0.70)]}},
        {"result": {"analogs": [_analog(["macro", "technical"], "bull_trend", "LONG", False, 0.75)]}},
    ]
    _attach_win_rate_stability(analogs, past_snapshots)

    stability = analogs[0]["win_rate_stability"]
    assert stability is not None
    assert stability["n"] == 3  # 2 geçmiş + 1 güncel
    assert abs(stability["mean"] - 0.75) < 1e-9


def test_only_matches_the_exact_same_bucket_key():
    """Farklı bir domain kombinasyonu/rejim/yön/reversing'e sahip geçmiş
    bir kova, YANLIŞ bir kovaya karışmamalı — anahtar tam eşleşmeli."""
    analogs = [_analog(["macro", "technical"], "bull_trend", "LONG", False, 0.80)]
    past_snapshots = [
        {"result": {"analogs": [_analog(["macro", "technical"], "bear_trend", "LONG", False, 0.10)]}},
        {"result": {"analogs": [_analog(["macro", "quant"], "bull_trend", "LONG", False, 0.90)]}},
    ]
    _attach_win_rate_stability(analogs, past_snapshots)

    # Hiçbir geçmiş kayıt eşleşmiyor -> sadece güncel ölçüm var -> fail-closed None.
    assert analogs[0]["win_rate_stability"] is None


def test_analog_key_is_order_independent_for_domains():
    a = _analog(["technical", "macro"], "bull_trend", "LONG", False, 0.5)
    b = _analog(["macro", "technical"], "bull_trend", "LONG", False, 0.9)
    assert _analog_key(a) == _analog_key(b)


def test_analog_key_does_not_crash_on_a_pre_faz_450_snapshot():
    """Faz 450 (2026-09-08) — 7 boyutlu genişletmeden ÖNCE kaydedilmiş
    gerçek geçmiş raporlar (historical_analog_snapshots) volatility_
    regime/structure_phase/trade_type İÇERMEZ. _analog_key() bunları
    okurken KeyError ile çökmemeli — win_rate_stability özelliğinin
    TAMAMEN kırılması anlamına gelirdi."""
    old_format = {
        "domains": ["macro", "technical"], "market_regime": "bull_trend",
        "direction": "LONG", "reversing": False, "win_rate": 0.8,
    }
    key = _analog_key(old_format)
    assert isinstance(key, str)
    # Eski format YENİ formatla (aynı domain/regime/direction/reversing
    # ama gerçek volatility_regime/structure_phase/trade_type ile) ASLA
    # çakışmamalı -- farklı bir istatistiksel evren, yanlışlıkla
    # karıştırılmamalı.
    new_format = _analog(["macro", "technical"], "bull_trend", "LONG", False, 0.8)
    assert key != _analog_key(new_format)
