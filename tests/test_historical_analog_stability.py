"""Faz 407 — kullanıcı isteği: "ölçtüğümüz her veri için zaman içindeki
stabilitesini de ölçelim." historical_analog_gatherer.py'nin her
kovaya (domains+market_regime+direction+reversing) geçmiş snapshot'lardan
win_rate_stability eklediğini doğruluyor — SADECE gözlem, hiçbir kova
filtrelenmiyor/reddedilmiyor."""
from services.historical_analog_gatherer import _analog_key, _attach_win_rate_stability


def _analog(domains, regime, direction, reversing, win_rate):
    return {
        "domains": domains, "market_regime": regime, "direction": direction,
        "reversing": reversing, "win_rate": win_rate,
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
