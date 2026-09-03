"""Faz 407 — analytics/feature_ic.py::attach_ic_stability()'nin her
feature'a geçmiş snapshot'lardan ic_stability eklediğini doğruluyor.
historical_analog/agent_combination_reliability'deki AYNI desen."""
from analytics.feature_ic import attach_ic_stability


def test_attaches_none_when_no_past_snapshots_exist():
    features = {"rsi": {"ic": 0.15, "p_value": 0.01, "sample_size": 100, "agent_domain": "technical"}}
    attach_ic_stability(features, past_snapshots=[])
    assert features["rsi"]["ic_stability"] is None


def test_attaches_real_stability_from_matching_past_snapshots():
    features = {"rsi": {"ic": 0.20, "p_value": 0.01, "sample_size": 100, "agent_domain": "technical"}}
    past_snapshots = [
        {"features": {"rsi": {"ic": 0.10}}},
        {"features": {"rsi": {"ic": 0.15}}},
    ]
    attach_ic_stability(features, past_snapshots)

    stability = features["rsi"]["ic_stability"]
    assert stability["n"] == 3
    assert abs(stability["mean"] - 0.15) < 1e-9


def test_does_not_mix_up_different_features():
    features = {"rsi": {"ic": 0.20, "p_value": 0.01, "sample_size": 100, "agent_domain": "technical"}}
    past_snapshots = [{"features": {"macd": {"ic": 0.90}}}]
    attach_ic_stability(features, past_snapshots)
    assert features["rsi"]["ic_stability"] is None


def test_a_new_feature_not_present_before_gets_none_not_a_crash():
    """Geçmiş snapshot'larda hiç var olmayan YENİ bir feature (henüz
    hiç ateşlenmemiş bir sinyal ilk kez örneklem eşiğini geçtiğinde)
    fail-closed None almalı, hata fırlatmamalı."""
    features = {"brand_new_feature": {"ic": 0.30, "p_value": 0.02, "sample_size": 25, "agent_domain": "quant"}}
    past_snapshots = [{"features": {"rsi": {"ic": 0.10}}}]
    attach_ic_stability(features, past_snapshots)
    assert features["brand_new_feature"]["ic_stability"] is None
