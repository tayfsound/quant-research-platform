"""Market State / Direction Motoru testleri — Faz 401 (Market State Katmanı Faz 1)."""
from market_data.features.market_state_engine import compute_market_state, market_state_reversing_for_decision


def test_bull_trend_maps_to_long_direction():
    result = compute_market_state({"long_term_trend_regime": "bull_trend", "hurst_exponent": 0.7})
    assert result["direction"] == "LONG"


def test_bear_trend_maps_to_short_direction():
    result = compute_market_state({"long_term_trend_regime": "bear_trend", "hurst_exponent": 0.7})
    assert result["direction"] == "SHORT"


def test_transition_maps_to_neutral_direction():
    result = compute_market_state({"long_term_trend_regime": "transition", "hurst_exponent": 0.5})
    assert result["direction"] == "NEUTRAL"


def test_insufficient_data_is_reported_honestly_not_invented():
    result = compute_market_state({"long_term_trend_regime": "insufficient_data", "hurst_exponent": 0.9})
    assert result["direction"] == "NEUTRAL"
    assert result["confidence"] == 0.0


def test_missing_fields_default_to_neutral_zero_confidence():
    result = compute_market_state({})
    assert result["direction"] == "NEUTRAL"
    assert result["confidence"] == 0.0


def test_confidence_derived_from_hurst_distance_from_random_walk():
    # hurst=0.5 -> tam rastgele yürüyüş -> güven 0.
    weak = compute_market_state({"long_term_trend_regime": "bull_trend", "hurst_exponent": 0.5})
    assert weak["confidence"] == 0.0
    # hurst=1.0 -> maksimum kalıcılık -> güven 1.
    strong = compute_market_state({"long_term_trend_regime": "bull_trend", "hurst_exponent": 1.0})
    assert strong["confidence"] == 1.0
    # Ara değer.
    mid = compute_market_state({"long_term_trend_regime": "bull_trend", "hurst_exponent": 0.75})
    assert mid["confidence"] == 0.5


def test_confidence_is_clipped_to_unit_interval():
    result = compute_market_state({"long_term_trend_regime": "bear_trend", "hurst_exponent": 0.0})
    assert result["confidence"] == 1.0


def test_missing_hurst_exponent_is_zero_confidence_not_invented():
    result = compute_market_state({"long_term_trend_regime": "bull_trend"})
    assert result["confidence"] == 0.0


def test_reversing_passes_through_regime_changepoint_detected():
    reversing = compute_market_state({
        "long_term_trend_regime": "bull_trend", "hurst_exponent": 0.7,
        "regime_changepoint_detected": True,
    })
    assert reversing["reversing"] is True

    not_reversing = compute_market_state({
        "long_term_trend_regime": "bull_trend", "hurst_exponent": 0.7,
        "regime_changepoint_detected": False,
    })
    assert not_reversing["reversing"] is False


def test_missing_changepoint_field_defaults_to_not_reversing():
    result = compute_market_state({"long_term_trend_regime": "bull_trend", "hurst_exponent": 0.7})
    assert result["reversing"] is False


def test_market_state_reversing_for_decision_extracts_the_flag():
    contributions = [
        {"type": "decision_fusion", "data": {"rejection": "x"}},
        {"type": "market_state", "data": {"direction": "SHORT", "confidence": 0.5, "reversing": True, "regime_label": "x"}},
    ]
    assert market_state_reversing_for_decision(contributions) is True


def test_market_state_reversing_for_decision_extracts_false_correctly():
    contributions = [
        {"type": "market_state", "data": {"direction": "LONG", "confidence": 0.5, "reversing": False, "regime_label": "x"}},
    ]
    assert market_state_reversing_for_decision(contributions) is False


def test_market_state_reversing_for_decision_none_when_no_such_entry():
    """Faz 401'den (2026-09-01) ÖNCEKİ kararlarda bu alan hiç yok --
    icat edilmiş bir değer asla üretilmez."""
    assert market_state_reversing_for_decision([{"type": "decision_fusion", "data": {}}]) is None
    assert market_state_reversing_for_decision([]) is None
    assert market_state_reversing_for_decision(None) is None


def test_regime_label_matches_compute_regime_v2_output_exactly():
    """Bu modül regime_engine.py::compute_regime_v2()'nin YERİNE geçmiyor
    — AYNI etiketi taşıyor, sadece ayrı bir direction/confidence/reversing
    ekliyor. İki modül asla farklı bir regime_label üretmemeli."""
    from market_data.features.regime_engine import compute_regime_v2

    features = {
        "long_term_trend_regime": "bear_trend", "volatility_regime": "high",
        "regime_changepoint_detected": True, "hurst_exponent": 0.3,
    }
    assert compute_market_state(features)["regime_label"] == compute_regime_v2(features)
