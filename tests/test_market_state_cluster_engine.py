"""Faz 401 — Market State Cluster Engine testleri. tests/
test_cross_symbol_correlation.py'deki AYNI fixture deseni (korelasyon
matrisini gerçekten üreten getiri dizileri)."""
from analytics.market_state_cluster_engine import compute_cluster_market_state


def _state(direction: str, reversing: bool = False) -> dict:
    return {"direction": direction, "confidence": 0.6, "reversing": reversing, "regime_label": "bull_trend_normal"}


def test_no_peers_leaves_cluster_fields_none():
    returns = {"A": [0.01, -0.02, 0.03, -0.01, 0.02]}
    states = {"A": _state("LONG")}
    result = compute_cluster_market_state(returns, states)
    assert result["A"]["peer_count"] == 0
    assert result["A"]["cluster_agreement"] is None
    assert result["A"]["cluster_reversing_fraction"] is None
    # Kendi market state alanları KORUNUYOR.
    assert result["A"]["direction"] == "LONG"


def test_uncorrelated_symbols_get_no_peers():
    returns = {
        "A": [0.01, -0.02, 0.03, -0.01, 0.02],
        "B": [-0.02, 0.03, -0.01, 0.02, -0.015],  # A ile negatif korele
    }
    states = {"A": _state("LONG"), "B": _state("LONG")}
    result = compute_cluster_market_state(returns, states)
    assert result["A"]["peer_count"] == 0
    assert result["B"]["peer_count"] == 0


def test_highly_correlated_same_direction_peers_show_full_agreement():
    base = [0.01, -0.02, 0.03, -0.01, 0.02, 0.015, -0.005]
    returns = {"A": base, "B": [r * 1.01 for r in base]}
    states = {"A": _state("LONG"), "B": _state("LONG")}
    result = compute_cluster_market_state(returns, states)
    assert result["A"]["peer_count"] == 1
    assert result["A"]["cluster_agreement"] == 1.0
    assert result["B"]["cluster_agreement"] == 1.0


def test_highly_correlated_but_opposite_direction_peers_show_zero_agreement():
    base = [0.01, -0.02, 0.03, -0.01, 0.02, 0.015, -0.005]
    returns = {"A": base, "B": [r * 1.01 for r in base]}
    states = {"A": _state("LONG"), "B": _state("SHORT")}
    result = compute_cluster_market_state(returns, states)
    assert result["A"]["peer_count"] == 1
    assert result["A"]["cluster_agreement"] == 0.0


def test_cluster_reversing_fraction_reflects_peer_reversing_flags():
    base = [0.01, -0.02, 0.03, -0.01, 0.02, 0.015, -0.005]
    returns = {"A": base, "B": [r * 1.01 for r in base], "C": [r * 0.99 for r in base]}
    states = {"A": _state("LONG"), "B": _state("LONG", reversing=True), "C": _state("LONG", reversing=False)}
    result = compute_cluster_market_state(returns, states)
    assert result["A"]["peer_count"] == 2
    assert result["A"]["cluster_reversing_fraction"] == 0.5


def test_missing_per_symbol_state_is_skipped_not_invented():
    returns = {"A": [0.01, -0.02, 0.03], "B": [0.011, -0.021, 0.031]}
    states = {"A": _state("LONG")}  # B'nin market state'i yok
    result = compute_cluster_market_state(returns, states)
    assert "B" not in result
    assert "A" in result
