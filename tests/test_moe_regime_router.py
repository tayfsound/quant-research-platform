"""MoE Regime Router testleri — Faz 369-393 (Cognitive Core 2.0)."""
from analytics.moe_regime_router import compute_moe_expert_weights


def test_high_hurst_tilts_toward_momentum():
    result = compute_moe_expert_weights(0.8)
    assert result["regime"] == "trending"
    assert result["momentum_weight"] > 1.0
    assert result["mean_reversion_weight"] < 1.0


def test_low_hurst_tilts_toward_mean_reversion():
    result = compute_moe_expert_weights(0.2)
    assert result["regime"] == "mean_reverting"
    assert result["mean_reversion_weight"] > 1.0
    assert result["momentum_weight"] < 1.0


def test_neutral_hurst_produces_no_tilt():
    result = compute_moe_expert_weights(0.5)
    assert result["regime"] == "neutral"
    assert result["momentum_weight"] == 1.0
    assert result["mean_reversion_weight"] == 1.0


def test_extreme_hurst_is_capped_at_max_tilt():
    result = compute_moe_expert_weights(1.0)
    assert abs(result["momentum_weight"] - 1.3) < 1e-6
    assert abs(result["mean_reversion_weight"] - 0.7) < 1e-6


def test_extreme_low_hurst_is_capped_at_max_tilt():
    result = compute_moe_expert_weights(0.0)
    assert abs(result["mean_reversion_weight"] - 1.3) < 1e-6
    assert abs(result["momentum_weight"] - 0.7) < 1e-6


def test_boundary_values_are_exactly_neutral_transition():
    trending_boundary = compute_moe_expert_weights(0.55)
    assert trending_boundary["regime"] == "trending"
    assert trending_boundary["momentum_weight"] == 1.0  # sınırda tilt=0

    reverting_boundary = compute_moe_expert_weights(0.45)
    assert reverting_boundary["regime"] == "mean_reverting"
    assert reverting_boundary["mean_reversion_weight"] == 1.0
