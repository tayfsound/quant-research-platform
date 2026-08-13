"""Deflated Sharpe Ratio testleri — Faz 669-693 (Cognitive Core 2.0 / M7)."""
import numpy as np

from analytics.backtest_validation import compute_deflated_sharpe_ratio


def _real_returns(mean: float, std: float, n: int, seed: int) -> list[float]:
    rng = np.random.default_rng(seed)
    return list(rng.normal(mean, std, n))


def test_high_sharpe_with_a_single_trial_scores_a_high_dsr():
    returns = _real_returns(mean=0.01, std=0.02, n=200, seed=1)
    result = compute_deflated_sharpe_ratio(returns, n_trials=1)
    assert result is not None
    assert result["deflated_sharpe_ratio"] > 0.9


def test_more_trials_deflates_the_same_sharpe_ratio():
    """AYNI getiri serisi, sadece kaç deneme yapıldığı farklı — çok deneme
    yapılmışsa (multiple testing), DSR daha DÜŞÜK olmalı (aynı Sharpe'ın
    şans eseri çıkma olasılığı artar)."""
    returns = _real_returns(mean=0.005, std=0.02, n=200, seed=2)
    few_trials = compute_deflated_sharpe_ratio(returns, n_trials=1)
    many_trials = compute_deflated_sharpe_ratio(returns, n_trials=500)
    assert many_trials["deflated_sharpe_ratio"] < few_trials["deflated_sharpe_ratio"]


def test_below_min_sample_size_is_fail_closed():
    assert compute_deflated_sharpe_ratio([0.01] * 5, n_trials=1) is None


def test_zero_trials_is_fail_closed():
    returns = _real_returns(mean=0.01, std=0.02, n=50, seed=3)
    assert compute_deflated_sharpe_ratio(returns, n_trials=0) is None


def test_constant_returns_are_fail_closed():
    assert compute_deflated_sharpe_ratio([0.01] * 50, n_trials=1) is None


def test_negative_sharpe_scores_a_low_dsr():
    returns = _real_returns(mean=-0.01, std=0.02, n=200, seed=4)
    result = compute_deflated_sharpe_ratio(returns, n_trials=1)
    assert result["deflated_sharpe_ratio"] < 0.5
    assert result["genuinely_skillful"] is False
