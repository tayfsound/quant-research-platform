"""Faz 352 — Regime Reversal Guardian, saf hesaplama testleri."""
from analytics.regime_reversal import consecutive_stop_streak


def _trade(exit_reason: str) -> dict:
    return {"outcome": {"exit_reason": exit_reason}}


def test_all_stop_losses_counts_full_length():
    trades = [_trade("stop_loss") for _ in range(5)]
    assert consecutive_stop_streak(trades) == 5


def test_streak_stops_at_first_non_stop_loss_going_backward():
    trades = [_trade("stop_loss"), _trade("stop_loss"), _trade("take_profit"), _trade("stop_loss")]
    assert consecutive_stop_streak(trades) == 2


def test_non_stop_loss_first_trade_returns_zero():
    trades = [_trade("take_profit"), _trade("stop_loss"), _trade("stop_loss")]
    assert consecutive_stop_streak(trades) == 0


def test_empty_list_returns_zero():
    assert consecutive_stop_streak([]) == 0


def test_missing_outcome_or_exit_reason_treated_as_non_stop():
    trades = [{"outcome": None}, _trade("stop_loss")]
    assert consecutive_stop_streak(trades) == 0

    trades2 = [{}, _trade("stop_loss")]
    assert consecutive_stop_streak(trades2) == 0
