"""Faz 362 — analytics/signal_persistence.py saf fonksiyon testleri."""
from analytics.signal_persistence import (
    consecutive_reversal_run_length,
    consistent_direction_run_length,
    find_optimal_persistence_threshold,
    find_optimal_reversal_exit_threshold,
    is_belief_reversal_exit_triggered,
    is_fresh_signal_blocked,
)


def test_run_length_zero_when_no_prior_decisions():
    assert consistent_direction_run_length([], "LONG") == 0


def test_run_length_zero_when_most_recent_disagrees():
    prior = [{"direction": "SHORT"}, {"direction": "LONG"}, {"direction": "LONG"}]
    assert consistent_direction_run_length(prior, "LONG") == 0


def test_run_length_counts_consecutive_agreement_from_most_recent():
    prior = [{"direction": "LONG"}, {"direction": "LONG"}, {"direction": "SHORT"}]
    assert consistent_direction_run_length(prior, "LONG") == 2


def test_run_length_stops_at_first_disagreement():
    prior = [{"direction": "LONG"}, {"direction": "SHORT"}, {"direction": "LONG"}, {"direction": "LONG"}]
    assert consistent_direction_run_length(prior, "LONG") == 1


def test_run_length_all_agree():
    prior = [{"direction": "LONG"}] * 5
    assert consistent_direction_run_length(prior, "LONG") == 5


def test_is_fresh_signal_blocked_below_threshold():
    assert is_fresh_signal_blocked(3, min_required_cycles=4)


def test_is_fresh_signal_blocked_at_threshold_is_not_blocked():
    assert not is_fresh_signal_blocked(4, min_required_cycles=4)


def test_is_fresh_signal_blocked_above_threshold_is_not_blocked():
    assert not is_fresh_signal_blocked(10, min_required_cycles=4)


def test_find_optimal_threshold_empty_input_fails_closed():
    result = find_optimal_persistence_threshold([])
    assert result["optimal_n"] is None
    assert result["table"] == []


def test_find_optimal_threshold_picks_total_pnl_maximizing_n():
    # run=0: 3 kayip islem (-10 her biri) -- toplam -30
    # run=1: 2 kucuk kazanc (+5 her biri) -- kumulatif(>=1) toplami: -30+...
    # asagidaki veriyle N=1'in toplam pnl'i (kumulatif >=1) en yuksek olmali.
    data = [
        (0, -10.0), (0, -10.0), (0, -10.0),
        (1, 50.0), (1, 50.0),
        (2, 1.0),
    ]
    result = find_optimal_persistence_threshold(data, max_n=3)
    # N=0 toplam: -30+50+50+1 = 71
    # N=1 toplam: 50+50+1 = 101  <- en yuksek
    # N=2 toplam: 1
    assert result["optimal_n"] == 1
    row_n1 = next(r for r in result["table"] if r["n"] == 1)
    assert row_n1["total_pnl"] == 101.0
    assert row_n1["count"] == 3


def test_find_optimal_threshold_table_covers_full_range_until_data_runs_out():
    data = [(0, 1.0), (1, 2.0)]
    result = find_optimal_persistence_threshold(data, max_n=5)
    ns = [row["n"] for row in result["table"]]
    assert ns == [0, 1]


def test_reversal_run_length_zero_when_no_prior_decisions():
    assert consecutive_reversal_run_length([], "LONG", min_confidence=0.65) == 0


def test_reversal_run_length_zero_when_most_recent_agrees_with_position():
    prior = [{"direction": "LONG", "confidence": 0.9}]
    assert consecutive_reversal_run_length(prior, "LONG", min_confidence=0.65) == 0


def test_reversal_run_length_zero_when_opposite_but_below_confidence():
    prior = [{"direction": "SHORT", "confidence": 0.5}]
    assert consecutive_reversal_run_length(prior, "LONG", min_confidence=0.65) == 0


def test_reversal_run_length_counts_consecutive_confident_opposite():
    prior = [
        {"direction": "SHORT", "confidence": 0.7},
        {"direction": "SHORT", "confidence": 0.8},
        {"direction": "LONG", "confidence": 0.9},
    ]
    assert consecutive_reversal_run_length(prior, "LONG", min_confidence=0.65) == 2


def test_reversal_run_length_stops_at_low_confidence_break():
    prior = [
        {"direction": "SHORT", "confidence": 0.7},
        {"direction": "SHORT", "confidence": 0.5},  # dusuk guven -- akisi kirar
        {"direction": "SHORT", "confidence": 0.9},
    ]
    assert consecutive_reversal_run_length(prior, "LONG", min_confidence=0.65) == 1


def test_is_belief_reversal_exit_triggered_below_threshold():
    assert not is_belief_reversal_exit_triggered(5, min_required_cycles=6)


def test_is_belief_reversal_exit_triggered_at_threshold():
    assert is_belief_reversal_exit_triggered(6, min_required_cycles=6)


def test_find_optimal_reversal_exit_threshold_empty_fails_closed():
    result = find_optimal_reversal_exit_threshold({})
    assert result["optimal_n"] is None
    assert result["table"] == []


def test_find_optimal_reversal_exit_threshold_picks_max_total_benefit():
    diffs_by_n = {
        1: [-100.0, -100.0, 5.0],   # toplam -195
        4: [-10.0, 5.0],             # toplam -5
        6: [10.0, 20.0, 5.0],        # toplam 35 <- en yuksek
    }
    result = find_optimal_reversal_exit_threshold(diffs_by_n)
    assert result["optimal_n"] == 6
    row = next(r for r in result["table"] if r["n"] == 6)
    assert row["total_benefit"] == 35.0
    assert row["better"] == 3
    assert row["worse"] == 0
