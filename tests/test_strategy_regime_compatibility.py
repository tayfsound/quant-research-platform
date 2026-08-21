"""analytics/strategy_regime_compatibility.py — Faz 338 (MetaStrategyAgent
v1). "Bu stratejinin şu anki piyasa rejiminde gerçek edge'i var mı?"
sorusuna GERÇEK verilerle cevap veren, ölçüm-only bir modül."""
from analytics.strategy_regime_compatibility import compute_strategy_regime_compatibility


def _records(strategy: str, regime: str, n: int, win_count: int) -> list[dict]:
    return [
        {"strategy": strategy, "market_regime": regime, "win": i < win_count}
        for i in range(n)
    ]


def test_empty_input_returns_empty_dict():
    assert compute_strategy_regime_compatibility([]) == {}


def test_below_min_group_size_is_excluded_but_overall_still_reported():
    records = _records("pump_fade", "bullish_low", n=5, win_count=4)
    result = compute_strategy_regime_compatibility(records, min_group_size=15)
    assert "pump_fade" in result
    assert result["pump_fade"]["overall_sample_size"] == 5
    assert result["pump_fade"]["by_regime"] == {}  # esik altinda, disarida


def test_regime_conditional_win_rate_and_delta_computed():
    """pump_fade bullish rejimde kötü (%20), bearish rejimde iyi (%90) —
    tam olarak bugünkü krizin ölçtüğü desen."""
    records = (
        _records("pump_fade", "bullish_normal", n=20, win_count=4)  # %20
        + _records("pump_fade", "bearish_normal", n=20, win_count=18)  # %90
    )
    result = compute_strategy_regime_compatibility(records, min_group_size=15)
    pf = result["pump_fade"]
    assert pf["overall_sample_size"] == 40
    assert pf["overall_win_rate"] == 0.55  # (4+18)/40
    assert pf["by_regime"]["bullish_normal"]["win_rate"] == 0.2
    assert pf["by_regime"]["bearish_normal"]["win_rate"] == 0.9
    assert pf["by_regime"]["bullish_normal"]["delta_vs_overall"] == -0.35
    assert pf["by_regime"]["bearish_normal"]["delta_vs_overall"] == 0.35


def test_multiple_strategies_are_kept_independent():
    records = (
        _records("pump_fade", "bullish_normal", n=20, win_count=4)
        + _records("ai_council", "bullish_normal", n=20, win_count=19)
    )
    result = compute_strategy_regime_compatibility(records, min_group_size=15)
    assert set(result.keys()) == {"pump_fade", "ai_council"}
    assert result["ai_council"]["by_regime"]["bullish_normal"]["win_rate"] == 0.95


def test_records_with_missing_fields_are_skipped():
    records = [
        {"strategy": "pump_fade", "market_regime": None, "win": True},
        {"strategy": None, "market_regime": "bullish_normal", "win": True},
        {"strategy": "pump_fade", "market_regime": "bullish_normal", "win": None},
    ]
    result = compute_strategy_regime_compatibility(records)
    assert result == {}
