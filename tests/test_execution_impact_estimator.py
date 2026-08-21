"""services/execution_impact_estimator.py — Faz 337. Kare-kök piyasa
etkisi modeli (Kyle 1985, Almgren-Chriss 2000) — alpha üretmiyor, sadece
tahmini yürütme maliyetini ölçüyor."""
from services.execution_impact_estimator import estimate_execution_cost_pct


def _book(best_bid=100.0, best_ask=100.1, bid_volume=1000.0, ask_volume=1000.0, spread_bps=10.0):
    return {
        "best_bid": best_bid, "best_ask": best_ask,
        "bid_volume": bid_volume, "ask_volume": ask_volume,
        "spread_bps": spread_bps,
    }


def test_returns_none_when_order_book_missing():
    assert estimate_execution_cost_pct(None, 1000.0, "LONG") is None
    assert estimate_execution_cost_pct({}, 1000.0, "LONG") is None


def test_returns_none_when_notional_not_positive():
    assert estimate_execution_cost_pct(_book(), 0.0, "LONG") is None
    assert estimate_execution_cost_pct(_book(), -100.0, "LONG") is None


def test_returns_none_when_relevant_side_volume_missing():
    book = _book(ask_volume=0.0)
    assert estimate_execution_cost_pct(book, 1000.0, "LONG") is None


def test_small_order_relative_to_liquidity_has_low_impact():
    # ask_volume=1000 @ price~100.1 -> mevcut likidite ~$100,100. $100
    # emir, likiditenin sadece ~%0.1'i -> depth_ratio küçük, impact küçük.
    result = estimate_execution_cost_pct(_book(), 100.0, "LONG")
    assert result is not None
    assert result["depth_ratio"] < 0.01
    assert result["impact_cost_pct"] < result["spread_cost_pct"]


def test_large_order_relative_to_liquidity_has_high_impact():
    # Mevcut likiditenin katları büyüklüğünde bir emir -> depth_ratio > 1,
    # impact_cost_pct spread_cost_pct'ten belirgin şekilde büyük olmalı.
    result = estimate_execution_cost_pct(_book(), 500_000.0, "LONG")
    assert result is not None
    assert result["depth_ratio"] > 1.0
    assert result["impact_cost_pct"] > result["spread_cost_pct"]


def test_long_uses_ask_side_short_uses_bid_side():
    book = _book(bid_volume=100.0, ask_volume=100000.0)
    long_result = estimate_execution_cost_pct(book, 50_000.0, "LONG")
    short_result = estimate_execution_cost_pct(book, 50_000.0, "SHORT")
    assert long_result is not None and short_result is not None
    # ask tarafinda cok daha fazla likidite var -> LONG'un impact'i cok daha kucuk olmali.
    assert long_result["impact_cost_pct"] < short_result["impact_cost_pct"]


def test_wider_spread_increases_spread_cost():
    tight = estimate_execution_cost_pct(_book(spread_bps=5.0), 1000.0, "LONG")
    wide = estimate_execution_cost_pct(_book(spread_bps=50.0), 1000.0, "LONG")
    assert wide["spread_cost_pct"] > tight["spread_cost_pct"]
