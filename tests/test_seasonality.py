"""Seasonality Detection testleri."""
from datetime import UTC, datetime

from analytics.seasonality import compute_day_of_week_seasonality, compute_hourly_seasonality


def _trade(opened_at: datetime, pnl: float) -> dict:
    return {"opened_at": opened_at, "pnl": pnl}


def test_hourly_seasonality_groups_by_utc_hour():
    trades = (
        [_trade(datetime(2026, 1, i + 1, 9, 0, tzinfo=UTC), pnl=5.0) for i in range(25)]
        + [_trade(datetime(2026, 1, i + 1, 22, 0, tzinfo=UTC), pnl=-5.0) for i in range(25)]
    )
    result = compute_hourly_seasonality(trades, min_bucket_size=20)
    assert "9" in result["buckets"]
    assert "22" in result["buckets"]
    assert result["buckets"]["9"]["win_rate"] == 1.0
    assert result["buckets"]["22"]["win_rate"] == 0.0
    assert result["buckets"]["9"]["sample_size"] == 25


def test_hourly_seasonality_detects_a_real_significant_difference():
    trades = (
        [_trade(datetime(2026, 1, i + 1, 9, 0, tzinfo=UTC), pnl=10.0 + i * 0.01) for i in range(30)]
        + [_trade(datetime(2026, 1, i + 1, 3, 0, tzinfo=UTC), pnl=-10.0 - i * 0.01) for i in range(30)]
    )
    result = compute_hourly_seasonality(trades, min_bucket_size=20)
    assert result["significance"]["p_value"] is not None
    assert result["significance"]["significant"] is True


def test_hourly_seasonality_buckets_below_min_size_are_excluded():
    trades = [_trade(datetime(2026, 1, 1, 5, 0, tzinfo=UTC), pnl=1.0) for _ in range(5)]
    result = compute_hourly_seasonality(trades, min_bucket_size=20)
    assert result["buckets"] == {}
    assert result["significance"]["p_value"] is None


def test_hourly_seasonality_significance_is_none_with_a_single_eligible_bucket():
    trades = [_trade(datetime(2026, 1, i + 1, 5, 0, tzinfo=UTC), pnl=1.0) for i in range(25)]
    result = compute_hourly_seasonality(trades, min_bucket_size=20)
    assert "5" in result["buckets"]
    assert result["significance"]["p_value"] is None
    assert result["significance"]["significant"] is None


def test_hourly_seasonality_skips_trades_missing_opened_at_or_pnl_without_crashing():
    trades = [{"opened_at": None, "pnl": 1.0}, {"opened_at": datetime(2026, 1, 1, tzinfo=UTC), "pnl": None}]
    result = compute_hourly_seasonality(trades, min_bucket_size=1)
    assert result["buckets"] == {}


def test_day_of_week_seasonality_uses_python_weekday_convention():
    monday = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)  # gerçekten Pazartesi
    assert monday.weekday() == 0
    trades = [_trade(monday, pnl=3.0) for _ in range(25)]
    result = compute_day_of_week_seasonality(trades, min_bucket_size=20)
    assert "0" in result["buckets"]
    assert result["buckets"]["0"]["sample_size"] == 25
