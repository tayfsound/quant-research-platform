"""Market World Model (Moving Block Bootstrap) testleri — Faz 901-940 (Cognitive Core 5.0-6.0)."""
from analytics.market_world_model import compute_block_bootstrap_paths


def test_constant_returns_produce_the_exact_compounded_result():
    returns = [0.01] * 20
    result = compute_block_bootstrap_paths(returns, block_size=3, path_length=10, n_paths=50)
    assert result is not None
    expected = (1.01 ** 10) - 1.0
    assert abs(result["mean_cumulative_return"] - expected) < 1e-6
    assert abs(result["p5_cumulative_return"] - expected) < 1e-6
    assert abs(result["worst_cumulative_return"] - expected) < 1e-6


def test_same_seed_is_reproducible():
    returns = [0.01, -0.02, 0.03, -0.01, 0.02, 0.01, -0.015, 0.025, 0.01, -0.005] * 3
    result_a = compute_block_bootstrap_paths(returns, block_size=3, path_length=15, n_paths=200, random_seed=7)
    result_b = compute_block_bootstrap_paths(returns, block_size=3, path_length=15, n_paths=200, random_seed=7)
    assert result_a == result_b


def test_percentile_ordering_is_sane():
    returns = [0.02, -0.03, 0.01, -0.01, 0.04, -0.02, 0.015, -0.005, 0.03, -0.01] * 3
    result = compute_block_bootstrap_paths(returns, block_size=4, path_length=20, n_paths=500)
    assert result["p5_cumulative_return"] <= result["mean_cumulative_return"] <= result["p95_cumulative_return"]
    assert result["worst_cumulative_return"] <= result["p5_cumulative_return"]


def test_insufficient_data_is_fail_closed():
    returns = [0.01] * 4
    assert compute_block_bootstrap_paths(returns, block_size=3, path_length=10) is None


def test_invalid_block_size_or_path_length_is_fail_closed():
    returns = [0.01] * 20
    assert compute_block_bootstrap_paths(returns, block_size=0, path_length=10) is None
    assert compute_block_bootstrap_paths(returns, block_size=3, path_length=0) is None
