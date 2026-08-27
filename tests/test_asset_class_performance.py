"""analytics/asset_class_performance.py — kullanıcı isteği (2026-08-27):
Bitcoin/Emtia/Hisse performans kartı."""
from analytics.asset_class_performance import compute_asset_class_performance


def _trade(symbol: str, pnl: float) -> dict:
    return {"symbol": symbol, "pnl": pnl}


def test_groups_symbols_into_three_broad_categories():
    trades = (
        [_trade("BTCUSDT", 1.0) for _ in range(5)]
        + [_trade("PAXGUSDT", 1.0) for _ in range(5)]
        + [_trade("AAPL", -1.0) for _ in range(5)]
    )
    result = compute_asset_class_performance(trades, min_sample_size=5)
    assert set(result.keys()) == {"Kripto", "Emtia", "Hisse Senedi"}
    assert result["Kripto"]["win_rate"] == 1.0
    assert result["Emtia"]["win_rate"] == 1.0
    assert result["Hisse Senedi"]["win_rate"] == 0.0


def test_gold_backed_and_precious_metal_future_merge_into_emtia():
    trades = [_trade("PAXGUSDT", 1.0) for _ in range(3)] + [_trade("GC=F", 1.0) for _ in range(3)]
    result = compute_asset_class_performance(trades, min_sample_size=5)
    assert result["Emtia"]["sample_size"] == 6


def test_equity_and_equity_index_merge_into_hisse_senedi():
    trades = [_trade("AAPL", 1.0) for _ in range(3)] + [_trade("^GSPC", 1.0) for _ in range(3)]
    result = compute_asset_class_performance(trades, min_sample_size=5)
    assert result["Hisse Senedi"]["sample_size"] == 6


def test_below_min_sample_size_is_excluded():
    trades = [_trade("BTCUSDT", 1.0) for _ in range(3)]
    result = compute_asset_class_performance(trades, min_sample_size=5)
    assert "Kripto" not in result


def test_unknown_symbol_is_excluded_not_forced_into_a_category():
    trades = [_trade("UNKNOWNTHING", 1.0) for _ in range(10)]
    result = compute_asset_class_performance(trades, min_sample_size=5)
    assert result == {}


def test_empty_input_is_fail_closed():
    assert compute_asset_class_performance([]) == {}
