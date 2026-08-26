"""Faz 363 — analytics/counterfactual_trade_replay.py'nin saf fonksiyonları
için birim testler. services/position_closer.py'nin GERÇEK, canlıda
kullanılan çıkış/breakeven mantığıyla davranışsal eşdeğerliği doğrular."""
from datetime import UTC, datetime

from analytics.counterfactual_trade_replay import (
    BreakevenSettings,
    check_exit,
    compute_ratcheted_stop,
    walk_price_path_to_exit,
)
from market_data.ingestion.ohlcv import OHLCV

_NO_RATCHET = BreakevenSettings(
    trigger_r_multiple=999.0, trailing_pct=0.0,
    progressive_lock_min_profit_r=999.0, progressive_lock_fraction=0.0,
)


def _bar(close: float) -> OHLCV:
    now = datetime.now(UTC)
    return OHLCV(timestamp=now, open=close, high=close, low=close, close=close, volume=1.0)


def test_check_exit_long_stop_loss():
    assert check_exit("LONG", 90.0, stop_loss_price=95.0, take_profit_price=110.0) == "stop_loss"


def test_check_exit_long_take_profit():
    assert check_exit("LONG", 111.0, stop_loss_price=95.0, take_profit_price=110.0) == "take_profit"


def test_check_exit_short_stop_loss():
    assert check_exit("SHORT", 110.0, stop_loss_price=105.0, take_profit_price=90.0) == "stop_loss"


def test_check_exit_short_take_profit():
    assert check_exit("SHORT", 89.0, stop_loss_price=105.0, take_profit_price=90.0) == "take_profit"


def test_check_exit_no_trigger_returns_none():
    assert check_exit("LONG", 100.0, stop_loss_price=95.0, take_profit_price=110.0) is None


def test_compute_ratcheted_stop_long_breakeven_trigger():
    """0.5R lehte hareket -> stop girişe (breakeven) çekilir."""
    settings = BreakevenSettings(
        trigger_r_multiple=0.5, trailing_pct=0.0,
        progressive_lock_min_profit_r=999.0, progressive_lock_fraction=0.0,
    )
    # entry=100, stop=90 (risk=10) -> 0.5R = 5 -> 105'te tetiklenir.
    new_stop = compute_ratcheted_stop("LONG", 100.0, 90.0, None, 105.0, settings)
    assert new_stop == 100.0


def test_compute_ratcheted_stop_never_loosens():
    """Fiyat gerilese bile stop asla eski, daha gevşek seviyeye dönmez."""
    settings = BreakevenSettings(
        trigger_r_multiple=0.5, trailing_pct=0.0,
        progressive_lock_min_profit_r=999.0, progressive_lock_fraction=0.0,
    )
    ratcheted = compute_ratcheted_stop("LONG", 100.0, 90.0, None, 105.0, settings)
    assert ratcheted == 100.0
    # Fiyat 102'ye gerilese bile stop 100'de kalmalı (candidates=[100, ...] max'ı 100 altına düşmez).
    still = compute_ratcheted_stop("LONG", 100.0, ratcheted, None, 102.0, settings)
    assert still == 100.0


def test_compute_ratcheted_stop_short_direction_mirrors_long():
    settings = BreakevenSettings(
        trigger_r_multiple=0.5, trailing_pct=0.0,
        progressive_lock_min_profit_r=999.0, progressive_lock_fraction=0.0,
    )
    # entry=100, stop=110 (risk=10) -> 0.5R=5 -> 95'te tetiklenir.
    new_stop = compute_ratcheted_stop("SHORT", 100.0, 110.0, None, 95.0, settings)
    assert new_stop == 100.0


def test_walk_price_path_to_exit_stops_at_first_real_trigger():
    bars = [_bar(101.0), _bar(102.0), _bar(94.0), _bar(120.0)]  # 3. barda stop tetiklenir
    result = walk_price_path_to_exit(
        bars, "LONG", entry_price=100.0, initial_stop_price=95.0, take_profit_price=110.0,
        breakeven_settings=_NO_RATCHET,
    )
    assert result["exit_reason"] == "stop_loss"
    assert result["exit_price"] == 94.0
    assert result["exit_bar_index"] == 2


def test_walk_price_path_to_exit_no_exit_within_bars_returns_none_honestly():
    bars = [_bar(101.0), _bar(102.0), _bar(103.0)]  # ne stop ne hedefe ulaşır
    result = walk_price_path_to_exit(
        bars, "LONG", entry_price=100.0, initial_stop_price=95.0, take_profit_price=110.0,
        breakeven_settings=_NO_RATCHET,
    )
    assert result["exit_reason"] is None
    assert result["exit_price"] is None


def test_walk_price_path_to_exit_breakeven_ratchet_prevents_full_loss():
    """Fiyat önce lehte gidip stop'u breakeven'e çeker, sonra tersine
    dönüp giriş civarına gelir -- tam stop mesafesini değil, breakeven'i
    yemeli (services/position_closer.py'nin Faz 268ae bulgusunun tam
    kanıtladığı senaryo)."""
    settings = BreakevenSettings(
        trigger_r_multiple=0.5, trailing_pct=0.0,
        progressive_lock_min_profit_r=999.0, progressive_lock_fraction=0.0,
    )
    # entry=100, stop=90 (risk=10). 105'e çıkar (0.5R=105 -> breakeven tetiklenir, stop=100),
    # sonra 100'e geri döner -> stop_loss (artık 100'de) tetiklenmeli, 90 değil.
    bars = [_bar(105.0), _bar(100.0)]
    result = walk_price_path_to_exit(
        bars, "LONG", entry_price=100.0, initial_stop_price=90.0, take_profit_price=200.0,
        breakeven_settings=settings,
    )
    assert result["exit_reason"] == "stop_loss"
    assert result["exit_price"] == 100.0  # 90 DEĞİL -- breakeven koruması çalıştı
