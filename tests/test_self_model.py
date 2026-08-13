"""Self-Model testleri — Faz 769-800 (Cognitive Core 3.0)."""
from analytics.self_model import compute_self_reliability_snapshot


def test_all_clean_signals_produce_high_reliability():
    result = compute_self_reliability_snapshot(
        ece=0.02, recent_dsr=0.97, kill_switch_active=False,
        known_feature_drift_count=0, concept_drift_detected=False,
    )
    assert result["overall_reliability"] == "high"
    assert result["reliability_flags"] == []


def test_kill_switch_active_is_always_untrustworthy():
    result = compute_self_reliability_snapshot(
        ece=0.02, recent_dsr=0.97, kill_switch_active=True,
        known_feature_drift_count=0, concept_drift_detected=False,
    )
    assert result["overall_reliability"] == "untrustworthy"
    assert "kill_switch_active" in result["reliability_flags"]


def test_low_dsr_is_untrustworthy_even_without_kill_switch():
    result = compute_self_reliability_snapshot(
        ece=0.02, recent_dsr=0.1, kill_switch_active=False,
        known_feature_drift_count=0, concept_drift_detected=False,
    )
    assert result["overall_reliability"] == "untrustworthy"


def test_poor_calibration_alone_degrades_but_does_not_untrust():
    result = compute_self_reliability_snapshot(
        ece=0.25, recent_dsr=0.97, kill_switch_active=False,
        known_feature_drift_count=0, concept_drift_detected=False,
    )
    assert result["overall_reliability"] == "degraded"
    assert "poor_calibration" in result["reliability_flags"]


def test_feature_and_concept_drift_are_both_flagged():
    result = compute_self_reliability_snapshot(
        ece=0.02, recent_dsr=0.97, kill_switch_active=False,
        known_feature_drift_count=3, concept_drift_detected=True,
    )
    assert result["overall_reliability"] == "degraded"
    assert "3_features_drifted" in result["reliability_flags"]
    assert "concept_drift_detected" in result["reliability_flags"]


def test_missing_optional_inputs_do_not_crash():
    result = compute_self_reliability_snapshot(
        ece=None, recent_dsr=None, kill_switch_active=False,
        known_feature_drift_count=0, concept_drift_detected=False,
    )
    assert result["overall_reliability"] == "high"
