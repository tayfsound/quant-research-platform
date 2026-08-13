"""Expected Utility ve Karar Teorisi (CRRA) testleri — Faz 619-643 (Cognitive Core 2.0)."""
import numpy as np

from analytics.expected_utility import compute_crra_utility


def test_gamma_zero_recovers_plain_expected_value():
    returns = [0.02, -0.01, 0.03, -0.02, 0.01, 0.02, -0.01, 0.015, 0.01, -0.005]
    result = compute_crra_utility(returns, gamma=0.0)
    assert result is not None
    assert abs(result["certainty_equivalent_return"] - float(np.mean(returns))) < 1e-9


def test_gamma_one_matches_log_utility_by_hand():
    returns = [0.05] * 10
    result = compute_crra_utility(returns, gamma=1.0)
    expected_eu = float(np.log(1.05))
    assert abs(result["expected_utility"] - expected_eu) < 1e-7


def test_higher_risk_aversion_penalizes_volatile_series_more():
    """Aynı ortalama getiriye sahip iki seri: biri sabit (varyanssız),
    diğeri aynı ortalamayı ama yüksek varyansla veriyor. Risk-aversion
    arttıkça (gamma>0), oynak serinin certainty_equivalent'i sabit
    seriden DAHA DÜŞÜK olmalı — standart risk-aversion özelliği."""
    stable = [0.01] * 20
    volatile = [0.21, -0.19] * 10  # ortalama aynı (0.01), varyans çok yüksek
    stable_result = compute_crra_utility(stable, gamma=2.0)
    volatile_result = compute_crra_utility(volatile, gamma=2.0)
    assert stable_result["certainty_equivalent_return"] > volatile_result["certainty_equivalent_return"]


def test_total_loss_or_worse_is_fail_closed():
    returns = [-1.5] + [0.01] * 10  # %150 kayıp — wealth_relative negatif
    assert compute_crra_utility(returns, gamma=1.0) is None


def test_below_min_sample_size_is_fail_closed():
    assert compute_crra_utility([0.01, 0.02], gamma=1.0) is None
