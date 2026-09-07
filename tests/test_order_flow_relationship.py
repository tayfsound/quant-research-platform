"""market_data/features/order_flow_relationship.py — Faz 436 (kullanıcı
önceliği ①, 2026-09-07). funding_rate TEK BAŞINA Faz 411'de gürültü
bulunmuştu — bu modül OI+Funding+Price'ı BİRLİKTE sınıflandırıyor,
gözlem-only, hiçbir agent skoruna girmiyor."""
from datetime import UTC, datetime, timedelta

from market_data.features.order_flow_relationship import compute_order_flow_relationship


def _snap(minutes_ago: int, price: float, open_interest: float | None, funding_rate: float | None = None) -> dict:
    ts = datetime(2026, 9, 7, 12, 0, tzinfo=UTC) - timedelta(minutes=minutes_ago)
    return {
        "time": ts, "best_bid": price, "best_ask": price,
        "open_interest": open_interest, "funding_rate": funding_rate,
    }


def test_returns_none_for_fewer_than_two_snapshots():
    assert compute_order_flow_relationship([]) is None
    assert compute_order_flow_relationship([_snap(0, 100.0, 1000.0)]) is None


def test_bullish_new_longs_when_price_and_oi_both_rise():
    snapshots = [_snap(30, 100.0, 1000.0, 0.0001), _snap(0, 101.0, 1050.0, 0.0002)]
    result = compute_order_flow_relationship(snapshots)
    assert result["category"] == "bullish_new_longs"
    assert result["price_change_pct"] > 0
    assert result["oi_change_pct"] > 0


def test_bullish_short_covering_when_price_rises_but_oi_falls():
    """Kullanıcının ana ayrımı: fiyat yükseliyor ama open interest
    DÜŞÜYORSA bu yeni bir yükseliş bahsi değil, kısa pozisyonların
    kapanması (short covering) — AYNI 'bullish' etiketi altında farklı
    bir olay."""
    snapshots = [_snap(30, 100.0, 1000.0), _snap(0, 101.0, 950.0)]
    result = compute_order_flow_relationship(snapshots)
    assert result["category"] == "bullish_short_covering"


def test_bearish_new_shorts_when_price_falls_and_oi_rises():
    snapshots = [_snap(30, 100.0, 1000.0), _snap(0, 99.0, 1050.0)]
    result = compute_order_flow_relationship(snapshots)
    assert result["category"] == "bearish_new_shorts"


def test_bearish_long_capitulation_when_price_and_oi_both_fall():
    snapshots = [_snap(30, 100.0, 1000.0), _snap(0, 99.0, 950.0)]
    result = compute_order_flow_relationship(snapshots)
    assert result["category"] == "bearish_long_capitulation"


def test_unclear_when_changes_are_below_threshold():
    snapshots = [_snap(30, 100.0, 1000.0), _snap(0, 100.0001, 1000.001)]
    result = compute_order_flow_relationship(snapshots)
    assert result["category"] == "unclear"


def test_unclear_when_open_interest_is_missing_spot_only_symbol():
    """Vadeli kontratı olmayan bir sembol — open_interest hep None,
    fail-closed 'unclear', icat edilmiş bir sınıflandırma yok."""
    snapshots = [_snap(30, 100.0, None), _snap(0, 105.0, None)]
    result = compute_order_flow_relationship(snapshots)
    assert result["category"] == "unclear"
    assert result["oi_change_pct"] is None


def test_snapshots_are_resorted_regardless_of_input_order():
    snapshots = [_snap(0, 101.0, 1050.0), _snap(30, 100.0, 1000.0)]  # ters sırada verildi
    result = compute_order_flow_relationship(snapshots)
    assert result["category"] == "bullish_new_longs"


def test_funding_rate_is_reported_from_the_latest_snapshot():
    snapshots = [_snap(30, 100.0, 1000.0, 0.0001), _snap(0, 101.0, 1050.0, 0.0009)]
    result = compute_order_flow_relationship(snapshots)
    assert result["funding_rate"] == 0.0009
