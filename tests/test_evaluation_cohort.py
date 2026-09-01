"""Faz 400 — analytics/evaluation_cohort.py saf fonksiyon testleri."""
from datetime import UTC, datetime

from analytics.evaluation_cohort import describe_evaluation_window


def test_describe_evaluation_window_reports_count_and_limit():
    trades = [{"closed_at": datetime(2026, 8, 1, tzinfo=UTC)}, {"closed_at": datetime(2026, 8, 2, tzinfo=UTC)}]
    result = describe_evaluation_window(trades, limit=500)
    assert result["n_trades"] == 2
    assert result["limit"] == 500
    assert result["exclude_experiment_buckets"] == []
    assert result["production_ai_council_filtered"] is False


def test_describe_evaluation_window_reports_earliest_and_latest_closed_at():
    trades = [
        {"closed_at": datetime(2026, 8, 5, tzinfo=UTC)},
        {"closed_at": datetime(2026, 8, 1, tzinfo=UTC)},
        {"closed_at": datetime(2026, 8, 10, tzinfo=UTC)},
    ]
    result = describe_evaluation_window(trades, limit=None)
    assert result["earliest_closed_at"] == datetime(2026, 8, 1, tzinfo=UTC).isoformat()
    assert result["latest_closed_at"] == datetime(2026, 8, 10, tzinfo=UTC).isoformat()


def test_describe_evaluation_window_ignores_missing_closed_at():
    trades = [{"closed_at": None}, {"closed_at": datetime(2026, 8, 1, tzinfo=UTC)}, {}]
    result = describe_evaluation_window(trades, limit=100)
    assert result["n_trades"] == 3
    assert result["earliest_closed_at"] == datetime(2026, 8, 1, tzinfo=UTC).isoformat()
    assert result["latest_closed_at"] == datetime(2026, 8, 1, tzinfo=UTC).isoformat()


def test_describe_evaluation_window_handles_empty_input():
    result = describe_evaluation_window([], limit=2000)
    assert result["n_trades"] == 0
    assert result["earliest_closed_at"] is None
    assert result["latest_closed_at"] is None


def test_describe_evaluation_window_reports_exclusions_and_production_filter():
    result = describe_evaluation_window(
        [], limit=5000, exclude_experiment_buckets=["pump_fade_v1", "basis_arb_v1"],
        production_ai_council_filtered=True,
    )
    assert result["exclude_experiment_buckets"] == ["pump_fade_v1", "basis_arb_v1"]
    assert result["production_ai_council_filtered"] is True
