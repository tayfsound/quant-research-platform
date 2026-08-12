"""Faz 268-sonrası: Cross-Symbol Correlation Filter."""
from risk.cross_symbol_correlation import (
    MAX_CONVICTION_DISCOUNT,
    compute_same_direction_correlation_discount,
)


def test_single_symbol_gets_no_discount():
    result = compute_same_direction_correlation_discount({"BTCUSDT": [0.01, -0.02, 0.03]}, {"BTCUSDT": "LONG"})
    assert result["BTCUSDT"] == 1.0


def test_uncorrelated_same_direction_symbols_get_no_discount():
    returns = {
        "A": [0.01, -0.02, 0.03, -0.01, 0.02],
        "B": [-0.02, 0.03, -0.01, 0.02, -0.015],  # A ile ters hareket -> negatif korelasyon
    }
    directions = {"A": "LONG", "B": "LONG"}
    result = compute_same_direction_correlation_discount(returns, directions)
    assert result["A"] == 1.0
    assert result["B"] == 1.0


def test_highly_correlated_same_direction_symbols_get_discounted():
    base = [0.01, -0.02, 0.03, -0.01, 0.02, 0.015, -0.005]
    returns = {"A": base, "B": [r * 1.01 for r in base]}  # neredeyse özdeş hareket
    directions = {"A": "LONG", "B": "LONG"}
    result = compute_same_direction_correlation_discount(returns, directions)
    assert result["A"] < 1.0
    assert result["B"] < 1.0
    assert result["A"] >= 1.0 - MAX_CONVICTION_DISCOUNT


def test_highly_correlated_but_opposite_direction_symbols_get_no_discount():
    """A LONG, B SHORT önerilmiş — ikisi birbirine yüksek korele olsa
    bile, ZATEN ters yönde bahis yapıyorlar, "kalabalık aynı yönde"
    riski yok."""
    base = [0.01, -0.02, 0.03, -0.01, 0.02, 0.015, -0.005]
    returns = {"A": base, "B": [r * 1.01 for r in base]}
    directions = {"A": "LONG", "B": "SHORT"}
    result = compute_same_direction_correlation_discount(returns, directions)
    assert result["A"] == 1.0
    assert result["B"] == 1.0


def test_discount_never_exceeds_the_maximum():
    base = list(range(1, 21))
    returns = {"A": [float(x) for x in base], "B": [float(x) for x in base], "C": [float(x) for x in base]}
    directions = {"A": "LONG", "B": "LONG", "C": "LONG"}
    result = compute_same_direction_correlation_discount(returns, directions)
    for multiplier in result.values():
        assert multiplier >= 1.0 - MAX_CONVICTION_DISCOUNT
        assert multiplier <= 1.0


def test_three_symbols_two_correlated_one_independent():
    base = [0.01, -0.02, 0.03, -0.01, 0.02, 0.015, -0.005]
    independent = [-0.01, 0.02, -0.03, 0.01, -0.02, -0.015, 0.005]  # A/B'nin ters aynası
    returns = {"A": base, "B": [r * 1.01 for r in base], "C": independent}
    directions = {"A": "LONG", "B": "LONG", "C": "LONG"}
    result = compute_same_direction_correlation_discount(returns, directions)
    assert result["A"] < 1.0
    assert result["B"] < 1.0
    assert result["C"] == 1.0  # A/B ile negatif korele, kendi başına indirim almamalı
