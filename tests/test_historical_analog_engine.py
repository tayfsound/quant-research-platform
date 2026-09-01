"""FIL Faz D — analytics/historical_analog_engine.py. Aynı kalıp tests/
test_agent_combination_reliability.py'yi izliyor (üçüncü eksen olarak
market_regime eklendiği için)."""
from datetime import UTC, datetime, timedelta

from analytics.historical_analog_engine import compute_historical_analogs


def _record(domains, regime, direction, win, closed_at=None, reversing=False):
    return {
        "agreeing_domains": frozenset(domains),
        "market_regime": regime,
        "direction": direction,
        "win": win,
        "closed_at": closed_at,
        "reversing": reversing,
    }


def test_empty_input_is_fail_closed():
    result = compute_historical_analogs([])
    assert result == {"analogs": [], "baseline_win_rate": None, "baseline_sample_size": 0}


def test_excludes_records_missing_market_regime_or_direction():
    records = [
        {"agreeing_domains": frozenset({"technical", "macro"}), "market_regime": None,
         "direction": "LONG", "win": True, "closed_at": None},
        {"agreeing_domains": frozenset({"technical", "macro"}), "market_regime": "bullish_low",
         "direction": None, "win": True, "closed_at": None},
    ]
    result = compute_historical_analogs(records)
    assert result == {"analogs": [], "baseline_win_rate": None, "baseline_sample_size": 0}


def test_excludes_groups_below_min_group_size():
    records = (
        [_record({"technical", "macro"}, "bullish_low", "LONG", True) for _ in range(5)]
        + [_record({"quant"}, "bullish_low", "LONG", False) for _ in range(50)]
    )
    result = compute_historical_analogs(records, combination_sizes=(2,), min_group_size=20)
    keys = {(tuple(a["domains"]), a["market_regime"], a["direction"]) for a in result["analogs"]}
    assert (("macro", "technical"), "bullish_low", "LONG") not in keys


def test_finds_a_strong_real_analog_and_separates_by_regime():
    """AYNI domain ikilisi iki farklı rejimde çok farklı performans
    gösteriyor — üçüncü eksenin (market_regime) gerçekten ayırt edici
    olduğunu doğrular."""
    records = []
    for i in range(40):
        records.append(_record({"technical", "macro"}, "bullish_low", "LONG", i < 38))  # %95
    for i in range(40):
        records.append(_record({"technical", "macro"}, "bearish_high", "LONG", i < 8))  # %20

    result = compute_historical_analogs(records, combination_sizes=(2,), min_group_size=20)
    bullish = next(a for a in result["analogs"] if a["market_regime"] == "bullish_low")
    bearish = next(a for a in result["analogs"] if a["market_regime"] == "bearish_high")
    assert bullish["win_rate"] == 0.95
    assert bearish["win_rate"] == 0.20
    assert bullish["sample_size"] == 40
    assert bearish["sample_size"] == 40


def test_direction_is_a_separate_grouping_axis():
    """AYNI domain ikilisi + AYNI rejim ama farklı yön — ayrı hücreler
    olarak raporlanmalı (kullanıcının P(LONG)/P(SHORT) ayrımı isteği)."""
    records = []
    for i in range(30):
        records.append(_record({"technical", "macro"}, "bullish_low", "LONG", i < 27))
    for i in range(30):
        records.append(_record({"technical", "macro"}, "bullish_low", "SHORT", i < 6))

    result = compute_historical_analogs(records, combination_sizes=(2,), min_group_size=20)
    long_analog = next(a for a in result["analogs"] if a["direction"] == "LONG")
    short_analog = next(a for a in result["analogs"] if a["direction"] == "SHORT")
    assert long_analog["win_rate"] == 0.90
    assert short_analog["win_rate"] == 0.20


def test_reversing_is_a_separate_grouping_axis():
    """Faz 404 — dördüncü eksen: AYNI domain ikilisi + AYNI rejim + AYNI
    yön ama piyasa tersine dönüyor mu dönmüyor mu farklı — ayrı hücreler
    olarak raporlanmalı (direction'ın kendi ayrı-eksen testiyle AYNI
    desen)."""
    records = []
    for i in range(30):
        records.append(_record({"technical", "macro"}, "bullish_low", "LONG", i < 27, reversing=False))
    for i in range(30):
        records.append(_record({"technical", "macro"}, "bullish_low", "LONG", i < 6, reversing=True))

    result = compute_historical_analogs(records, combination_sizes=(2,), min_group_size=20)
    calm = next(a for a in result["analogs"] if a["reversing"] is False)
    reversing = next(a for a in result["analogs"] if a["reversing"] is True)
    assert calm["win_rate"] == 0.90
    assert reversing["win_rate"] == 0.20


def test_records_with_missing_or_non_bool_reversing_are_excluded_fail_closed():
    """Faz 404 — reversing SADECE Faz 401'den (2026-09-01) sonraki
    kararlarda var; eski kararlarda hiç yok (None). İcat edilmiş bir
    reversing değeri asla varsayılmamalı — bu kayıtlar örneklemden
    tamamen dışlanır."""
    records = [
        {"agreeing_domains": frozenset({"technical", "macro"}), "market_regime": "bullish_low",
         "direction": "LONG", "win": True, "closed_at": None, "reversing": None},
        {"agreeing_domains": frozenset({"technical", "macro"}), "market_regime": "bullish_low",
         "direction": "LONG", "win": True, "closed_at": None},  # reversing hiç yok
    ]
    result = compute_historical_analogs(records)
    assert result == {"analogs": [], "baseline_win_rate": None, "baseline_sample_size": 0}


def test_gate_eligible_requires_fdr_and_oos_and_effective_sample_size_together():
    base_time = datetime(2026, 8, 1, tzinfo=UTC)
    strong = [
        _record({"technical", "macro"}, "bullish_low", "LONG", i % 10 != 0, base_time + timedelta(hours=i))
        for i in range(40)
    ]
    baseline = [
        _record({"quant"}, "bullish_low", "LONG", i < 10, base_time + timedelta(hours=i))
        for i in range(40)
    ]
    result = compute_historical_analogs(strong + baseline, combination_sizes=(2,), min_group_size=20)
    analog = next(a for a in result["analogs"] if set(a["domains"]) == {"technical", "macro"})
    assert analog["fdr_significant"] is True
    assert analog["oos_survival"] is True
    assert analog["effective_sample_size"] >= 20
    assert analog["gate_eligible"] is True

    # closed_at yoksa (oos_survival=None) AYNI güçlü desen bile gate_eligible=False olmalı.
    strong_no_dates = [_record({"technical", "macro"}, "bullish_low", "LONG", i % 10 != 0) for i in range(40)]
    baseline_no_dates = [_record({"quant"}, "bullish_low", "LONG", i < 10) for i in range(40)]
    result2 = compute_historical_analogs(strong_no_dates + baseline_no_dates, combination_sizes=(2,), min_group_size=20)
    analog2 = next(a for a in result2["analogs"] if set(a["domains"]) == {"technical", "macro"})
    assert analog2["oos_survival"] is None
    assert analog2["gate_eligible"] is False


def test_noise_does_not_survive_fdr():
    """Rastgele/dengeli win-loss dağılımı (baseline'dan istatistiksel
    olarak ayırt edilemez) fdr_significant=False kalmalı."""
    records = [_record({"technical", "macro"}, "bullish_low", "LONG", i % 2 == 0) for i in range(40)]
    records += [_record({"quant"}, "bullish_low", "LONG", i % 2 == 0) for i in range(40)]
    result = compute_historical_analogs(records, combination_sizes=(2,), min_group_size=20)
    analog = next(a for a in result["analogs"] if set(a["domains"]) == {"technical", "macro"})
    assert analog["fdr_significant"] is False
    assert analog["gate_eligible"] is False
