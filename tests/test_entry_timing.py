"""Entry Timing testleri — Faz 594-618 (Cognitive Core 2.0 / M5)."""
from analytics.entry_timing import compute_immediate_adverse_excursion_rate


def _trade(mae_pct: float, time_to_mae_seconds: float) -> dict:
    return {"mae_pct": mae_pct, "time_to_mae_seconds": time_to_mae_seconds}


def test_detects_high_immediate_adverse_excursion_rate():
    trades = [_trade(-0.02, 30.0) for _ in range(18)] + [_trade(-0.01, 600.0) for _ in range(2)]
    result = compute_immediate_adverse_excursion_rate(trades, immediate_window_seconds=60.0)
    assert result is not None
    assert result["immediate_mae_rate"] == 0.9
    assert result["immediate_mae_count"] == 18


def test_detects_low_immediate_adverse_excursion_rate():
    trades = [_trade(-0.01, 600.0) for _ in range(18)] + [_trade(-0.02, 30.0) for _ in range(2)]
    result = compute_immediate_adverse_excursion_rate(trades, immediate_window_seconds=60.0)
    assert result["immediate_mae_rate"] == 0.1


def test_reports_average_mae_split_by_immediacy():
    trades = [_trade(-0.05, 10.0) for _ in range(10)] + [_trade(-0.01, 500.0) for _ in range(10)]
    result = compute_immediate_adverse_excursion_rate(trades, immediate_window_seconds=60.0)
    assert abs(result["avg_mae_pct_when_immediate"] - 0.05) < 1e-9
    assert abs(result["avg_mae_pct_when_later"] - 0.01) < 1e-9


def test_below_min_sample_size_is_fail_closed():
    trades = [_trade(-0.02, 30.0) for _ in range(5)]
    assert compute_immediate_adverse_excursion_rate(trades, immediate_window_seconds=60.0) is None


def test_trades_missing_fields_are_skipped_without_crashing():
    trades = [{"mae_pct": None, "time_to_mae_seconds": None}] * 25
    assert compute_immediate_adverse_excursion_rate(trades, immediate_window_seconds=60.0) is None
