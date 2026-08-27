"""analytics/regime_performance.py — kullanıcı isteği (2026-08-27):
REJİME GÖRE AI KONSEYİ GİRİŞLERİ kartındaki butonlara başarı oranı."""
from analytics.regime_performance import compute_regime_performance


def _trade(regime: str, pnl: float) -> dict:
    return {"market_regime": regime, "pnl": pnl}


def test_groups_by_market_regime():
    trades = [_trade("bullish_low", 1.0) for _ in range(5)] + [_trade("bearish_high", -1.0) for _ in range(5)]
    result = compute_regime_performance(trades, min_sample_size=5)
    assert result["bullish_low"]["win_rate"] == 1.0
    assert result["bearish_high"]["win_rate"] == 0.0


def test_below_min_sample_size_is_excluded():
    trades = [_trade("bullish_low", 1.0) for _ in range(3)]
    result = compute_regime_performance(trades, min_sample_size=5)
    assert "bullish_low" not in result


def test_missing_regime_is_skipped_not_bucketed():
    trades = [_trade(None, 1.0) for _ in range(10)]
    result = compute_regime_performance(trades, min_sample_size=5)
    assert result == {}


def test_empty_input_is_fail_closed():
    assert compute_regime_performance([]) == {}
