"""Adaptive Barrier Engine testleri — Faz 494-518 (Cognitive Core 2.0 / M3)."""
from datetime import UTC, datetime, timedelta

from analytics.adaptive_barrier_engine import recommend_barrier
from analytics.mae_mfe import MIN_DISTINCT_DAYS, compute_optimal_barrier


def _barrier_trade(mae_pct, mfe_pct, time_to_mae=100.0, time_to_mfe=50.0, direction="LONG",
                    regime="bull_trend", volatility_regime="normal", confidence=0.7, closed_at=None) -> dict:
    return {
        "mae_pct": mae_pct, "mfe_pct": mfe_pct,
        "time_to_mae_seconds": time_to_mae, "time_to_mfe_seconds": time_to_mfe,
        "direction": direction, "regime": regime,
        "volatility_regime": volatility_regime, "confidence": confidence,
        "closed_at": closed_at,
    }


def _spread_over_distinct_days(n: int) -> list[datetime]:
    """Faz 368 — compute_optimal_barrier artık MIN_DISTINCT_DAYS de
    istiyor (bkz. o modülün notu) — tek bir kova tek bir dar tarihsel
    pencereden gelmesin diye."""
    base = datetime(2026, 8, 1, tzinfo=UTC)
    days = max(MIN_DISTINCT_DAYS, 1)
    return [base + timedelta(days=i % days, hours=i) for i in range(n)]


def test_recommend_barrier_finds_the_real_precomputed_bucket():
    dates = _spread_over_distinct_days(30)
    trades = [
        _barrier_trade(mae_pct=-0.01, mfe_pct=0.03, time_to_mae=100.0, time_to_mfe=50.0, closed_at=dates[i])
        for i in range(30)
    ]
    barrier_table = compute_optimal_barrier(trades, group_by=("direction",), min_group_size=20, min_decisive_count=20)

    context = {"direction": "LONG"}
    result = recommend_barrier(context, barrier_table, group_by=("direction",))
    assert result is not None
    assert abs(result["sl_pct"] - 0.01) < 1e-9
    assert abs(result["tp_pct"] - 0.03) < 1e-9


def test_recommend_barrier_returns_none_for_an_unseen_bucket():
    trades = [_barrier_trade(mae_pct=-0.01, mfe_pct=0.03) for _ in range(30)]
    barrier_table = compute_optimal_barrier(trades, group_by=("direction",), min_group_size=20, min_decisive_count=20)

    context = {"direction": "SHORT"}  # hiç SHORT trade yok
    assert recommend_barrier(context, barrier_table, group_by=("direction",)) is None


def test_recommend_barrier_handles_confidence_bucketing_consistently():
    dates = _spread_over_distinct_days(30)
    trades = [
        _barrier_trade(mae_pct=-0.01, mfe_pct=0.03, confidence=0.72, closed_at=dates[i]) for i in range(30)
    ]
    barrier_table = compute_optimal_barrier(
        trades, group_by=("confidence",), min_group_size=20, min_decisive_count=20,
    )

    # 0.72 -> "0.7-0.8" kovası (mae_mfe._confidence_bucket ile AYNI mantık)
    result = recommend_barrier({"confidence": 0.75}, barrier_table, group_by=("confidence",))
    assert result is not None


def test_recommend_barrier_on_empty_table_is_fail_closed():
    assert recommend_barrier({"direction": "LONG"}, {}, group_by=("direction",)) is None
