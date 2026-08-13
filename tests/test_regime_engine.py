"""Piyasa Rejimi Motoru v2 testleri — Faz 319-343 (Cognitive Core 2.0)."""
from market_data.features.regime_engine import compute_regime_v2


def test_combines_trend_regime_and_volatility_regime():
    label = compute_regime_v2({"long_term_trend_regime": "bull_trend", "volatility_regime": "high"})
    assert label == "bull_trend_high"


def test_insufficient_trend_data_is_reported_honestly():
    label = compute_regime_v2({"long_term_trend_regime": "insufficient_data", "volatility_regime": "high"})
    assert label == "insufficient_data"


def test_missing_trend_regime_defaults_to_insufficient_data():
    assert compute_regime_v2({}) == "insufficient_data"


def test_missing_volatility_regime_defaults_to_normal():
    label = compute_regime_v2({"long_term_trend_regime": "bear_trend"})
    assert label == "bear_trend_normal"


def test_changepoint_detected_appends_reversing_suffix():
    label = compute_regime_v2({
        "long_term_trend_regime": "bull_trend", "volatility_regime": "low",
        "regime_changepoint_detected": True,
    })
    assert label == "bull_trend_low_reversing"


def test_no_changepoint_has_no_suffix():
    label = compute_regime_v2({
        "long_term_trend_regime": "bull_trend", "volatility_regime": "low",
        "regime_changepoint_detected": False,
    })
    assert label == "bull_trend_low"


def test_missing_changepoint_field_defaults_to_no_suffix():
    label = compute_regime_v2({"long_term_trend_regime": "transition", "volatility_regime": "normal"})
    assert label == "transition_normal"
