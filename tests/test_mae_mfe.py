"""MAE/MFE ölçüm katmanı testleri."""
from datetime import UTC, datetime, timedelta

from analytics.mae_mfe import compute_mae_mfe
from market_data.ingestion.ohlcv import OHLCV


def _bar(t: int, open_: float, high: float, low: float, close: float) -> OHLCV:
    return OHLCV(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=t),
        open=open_, high=high, low=low, close=close, volume=100.0,
    )


def test_long_mae_is_the_worst_dip_below_entry():
    bars = [
        _bar(0, 100, 100.5, 99.5, 100),
        _bar(1, 100, 100.2, 97.0, 98.0),   # en kötü dip: low=97.0
        _bar(2, 98, 99.0, 98.5, 99.0),
    ]
    result = compute_mae_mfe("LONG", entry_price=100.0, bars=bars)
    assert abs(result["mae_pct"] - (-0.03)) < 1e-6
    assert result["time_to_mae_seconds"] == 60.0


def test_long_mfe_is_the_best_rally_above_entry():
    bars = [
        _bar(0, 100, 100.5, 99.5, 100),
        _bar(1, 100, 104.0, 99.8, 103.0),  # en iyi zirve: high=104.0
        _bar(2, 103, 103.5, 102.0, 102.5),
    ]
    result = compute_mae_mfe("LONG", entry_price=100.0, bars=bars)
    assert abs(result["mfe_pct"] - 0.04) < 1e-6
    assert result["time_to_mfe_seconds"] == 60.0


def test_short_direction_signs_are_mirrored():
    bars = [
        _bar(0, 100, 100.5, 99.5, 100),
        _bar(1, 100, 103.0, 98.0, 99.0),  # SHORT için: high=103 aleyhte, low=98 lehte
    ]
    result = compute_mae_mfe("SHORT", entry_price=100.0, bars=bars)
    assert abs(result["mae_pct"] - (-0.03)) < 1e-6  # (100-103)/100
    assert abs(result["mfe_pct"] - 0.02) < 1e-6      # (100-98)/100


def test_a_trade_that_hit_stop_but_had_high_mfe_is_distinguishable():
    """Kullanıcının tam senaryosu: SL olmuş ama aslında TP'ye gidecek
    kadar potansiyeli varmış — yüksek MFE, düşük (SL'ye yakın) MAE."""
    bars = [
        _bar(0, 100, 100.2, 99.9, 100),
        _bar(1, 100, 101.8, 99.9, 101.5),   # MFE: +1.8% — gerçek potansiyel vardı
        _bar(2, 101.5, 101.6, 99.7, 99.8),  # MAE: -0.3% — sonra stop'a takıldı
    ]
    result = compute_mae_mfe("LONG", entry_price=100.0, bars=bars)
    assert result["mfe_pct"] > 0.017
    assert result["mae_pct"] < 0.0
    assert abs(result["mae_pct"]) < 0.005  # MAE küçük — sorun entry değil, dar SL


def test_entry_price_zero_is_handled_fail_closed():
    result = compute_mae_mfe("LONG", entry_price=0.0, bars=[_bar(0, 1, 1, 1, 1)])
    assert result["mae_pct"] is None
    assert result["mfe_pct"] is None


def test_empty_bars_is_handled_fail_closed():
    result = compute_mae_mfe("LONG", entry_price=100.0, bars=[])
    assert result["mae_pct"] is None
