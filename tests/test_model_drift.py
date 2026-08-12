"""Model Drift Detection (PSI/KS-test) testleri."""
import random

from analytics.model_drift import compute_feature_drift


def _decision(features: dict) -> dict:
    return {
        "agent_contributions": [
            {"type": "market_snapshot", "data": {"symbol": "BTCUSDT", "features": features}},
        ],
    }


def test_a_clearly_shifted_distribution_is_flagged_as_drift():
    """Baseline (eski, ESKİDEN YENİYE listede SONDA) RSI 40-60 aralığında,
    recent (yeni, listede BAŞTA — list_recent DESC sırayla döner) RSI
    80-100 aralığında — gerçek, belirgin bir rejim kayması."""
    rng = random.Random(42)
    recent = [_decision({"RSI": 80 + rng.random() * 20}) for _ in range(60)]  # yeni -> listenin başı
    baseline = [_decision({"RSI": 40 + rng.random() * 20}) for _ in range(60)]  # eski -> listenin sonu
    decisions = recent + baseline  # list_recent() DESC (en yeni ilk) sırasını taklit ediyor

    result = compute_feature_drift(decisions, split_frac=0.5, min_window_size=30)
    assert "RSI" in result
    assert result["RSI"]["drift_detected"] is True
    assert result["RSI"]["psi"] >= 0.25
    assert result["RSI"]["baseline_n"] == 60
    assert result["RSI"]["recent_n"] == 60


def test_an_unchanged_distribution_is_not_flagged():
    rng = random.Random(7)
    decisions = [_decision({"RSI": 45 + rng.random() * 10}) for _ in range(120)]

    result = compute_feature_drift(decisions, split_frac=0.5, min_window_size=30)
    assert "RSI" in result
    assert result["RSI"]["drift_detected"] is False
    assert result["RSI"]["psi"] < 0.25


def test_insufficient_sample_size_is_excluded_fail_closed():
    decisions = [_decision({"RSI": 50.0}) for _ in range(10)]
    result = compute_feature_drift(decisions, split_frac=0.5, min_window_size=30)
    assert "RSI" not in result


def test_categorical_features_are_not_included():
    decisions = [_decision({"trend": "bullish", "RSI": 50.0 + i}) for i in range(60)]
    result = compute_feature_drift(decisions, split_frac=0.5, min_window_size=20)
    assert "trend" not in result
    assert "RSI" in result


def test_a_constant_baseline_produces_no_meaningful_psi():
    decisions = [_decision({"constant_feature": 1.0}) for _ in range(60)]
    result = compute_feature_drift(decisions, split_frac=0.5, min_window_size=20)
    assert "constant_feature" not in result


def test_decisions_without_market_snapshot_are_ignored_without_crashing():
    decisions = [{"agent_contributions": [{"type": "risk_evaluation", "data": {}}]} for _ in range(40)]
    result = compute_feature_drift(decisions, split_frac=0.5, min_window_size=10)
    assert result == {}
