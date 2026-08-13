"""SL Sonrası Fiyat Geri Dönüşü testleri — Faz 268-sonrası (kullanıcı isteği)."""
from datetime import UTC, datetime, timedelta

from analytics.sl_recovery_analysis import compute_post_exit_recovery
from market_data.ingestion.ohlcv import OHLCV


def _bar(t_minutes: int, open_: float, high: float, low: float, close: float) -> OHLCV:
    return OHLCV(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=t_minutes),
        open=open_, high=high, low=low, close=close, volume=100.0,
    )


def test_returns_none_fields_when_no_post_exit_bars():
    result = compute_post_exit_recovery("LONG", 100.0, [])
    assert result["recovered_to_breakeven"] is None
    assert result["worst_pct_after_exit"] is None


def test_long_recovers_to_breakeven_after_going_deeper_first():
    # SL'e 95'te takıldı (entry=100). Sonrasında önce 90'a kadar iniyor
    # (worst), sonra geri 100'ün üstüne dönüyor (recovery).
    bars = [
        _bar(0, 95.0, 95.5, 92.0, 93.0),
        _bar(1, 93.0, 93.5, 90.0, 91.0),   # worst: low=90 -> -10%
        _bar(2, 91.0, 101.0, 90.5, 100.5),  # high=101 -> breakeven aşıldı
    ]
    result = compute_post_exit_recovery("LONG", entry_price=100.0, post_exit_bars=bars)
    assert result["recovered_to_breakeven"] is True
    assert abs(result["worst_pct_after_exit"] - (-0.10)) < 1e-9
    assert result["time_to_recovery_seconds"] == 120.0  # bar index 2, t=2dk


def test_long_never_recovers_within_the_given_window():
    bars = [
        _bar(0, 95.0, 95.5, 92.0, 93.0),
        _bar(1, 93.0, 94.0, 88.0, 89.0),
    ]
    result = compute_post_exit_recovery("LONG", entry_price=100.0, post_exit_bars=bars)
    assert result["recovered_to_breakeven"] is False
    assert result["time_to_recovery_seconds"] is None
    assert abs(result["worst_pct_after_exit"] - (-0.12)) < 1e-9


def test_short_recovers_to_breakeven_after_going_deeper_first():
    # SHORT SL'e 105'te takıldı (entry=100). Sonrasında önce 112'ye kadar
    # çıkıyor (worst, SHORT için aleyhte), sonra geri 100'ün altına dönüyor.
    bars = [
        _bar(0, 105.0, 108.0, 104.5, 107.0),
        _bar(1, 107.0, 112.0, 106.0, 110.0),  # worst: high=112 -> -12%
        _bar(2, 110.0, 110.5, 99.0, 99.5),    # low=99 -> breakeven aşıldı
    ]
    result = compute_post_exit_recovery("SHORT", entry_price=100.0, post_exit_bars=bars)
    assert result["recovered_to_breakeven"] is True
    assert abs(result["worst_pct_after_exit"] - (-0.12)) < 1e-9
    assert result["time_to_recovery_seconds"] == 120.0


def test_target_pct_reports_whether_the_original_take_profit_would_have_been_reached():
    # LONG, entry=100, SL sonrası fiyat 106'ya kadar çıkıyor -> %5 hedefe ulaşıyor.
    bars = [
        _bar(0, 95.0, 96.0, 94.0, 95.5),
        _bar(1, 95.5, 106.0, 95.0, 105.0),
    ]
    result = compute_post_exit_recovery("LONG", entry_price=100.0, post_exit_bars=bars, target_pct=0.05)
    assert result["reached_target"] is True
    assert result["time_to_target_seconds"] == 60.0


def test_target_pct_false_when_never_reached():
    bars = [_bar(0, 95.0, 96.0, 94.0, 95.5)]
    result = compute_post_exit_recovery("LONG", entry_price=100.0, post_exit_bars=bars, target_pct=0.05)
    assert result["reached_target"] is False
    assert result["time_to_target_seconds"] is None
