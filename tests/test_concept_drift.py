"""Online Learning ve Concept Drift testleri — Faz 719-743 (Cognitive Core 2.0 / M9)."""
from datetime import UTC, datetime

from analytics.concept_drift import collapse_batch_closed_trades, compute_concept_drift


def test_detects_a_real_significant_accuracy_shift():
    baseline = [True] * 40 + [False] * 10  # %80 doğruluk
    recent = [True] * 10 + [False] * 40  # %20 doğruluk
    result = compute_concept_drift(baseline, recent)
    assert result is not None
    assert result["drift_detected"] is True
    assert result["baseline_win_rate"] == 0.8
    assert result["recent_win_rate"] == 0.2


def test_stable_accuracy_is_not_flagged():
    baseline = [True] * 30 + [False] * 20  # %60
    recent = [True] * 28 + [False] * 22  # %56 — küçük, anlamsız fark
    result = compute_concept_drift(baseline, recent)
    assert result["drift_detected"] is False


def test_below_min_sample_size_is_fail_closed():
    assert compute_concept_drift([True] * 5, [True] * 30) is None
    assert compute_concept_drift([True] * 30, [True] * 5) is None


def test_degenerate_all_same_outcome_is_handled_gracefully():
    baseline = [True] * 30
    recent = [True] * 30
    result = compute_concept_drift(baseline, recent)
    # Ya dürüstçe None (test tanımsız) ya da gerçek %100/%100 ile drift yok.
    assert result is None or (result["baseline_win_rate"] == 1.0 and result["drift_detected"] is False)


def test_collapse_batch_closed_trades_merges_same_symbol_same_instant_legs():
    """Faz 398 — gerçek olay: 2026-08-27 GC=F/XAUTUSDT piramit kümesi,
    aynı close_due_positions taramasında (aynı closed_at) birlikte
    kapanan 10 bacak, tek bir gerçek kararmış gibi TEK gruba inmeli --
    toplam pnl negatifse tek bir kayıp, pozitifse tek bir kazanç."""
    t = datetime(2026, 8, 27, 2, 11, 56, 393192, tzinfo=UTC)
    trades = [
        {"symbol": "GC=F", "closed_at": t, "pnl": -44.43},
        {"symbol": "GC=F", "closed_at": t, "pnl": -30.84},
        {"symbol": "GC=F", "closed_at": t, "pnl": -72.13},
    ]
    result = collapse_batch_closed_trades(trades)
    assert len(result) == 1
    assert result[0]["symbol"] == "GC=F"
    assert result[0]["leg_count"] == 3
    assert round(result[0]["pnl"], 2) == round(-44.43 - 30.84 - 72.13, 2)


def test_collapse_batch_closed_trades_keeps_different_symbols_in_the_same_sweep_separate():
    """Aynı taramada (aynı closed_at) ama FARKLI sembollerin kapanması --
    ilgisiz, ayrı tezler, birleştirilmemeli."""
    t = datetime(2026, 8, 27, 2, 11, 56, tzinfo=UTC)
    trades = [
        {"symbol": "GC=F", "closed_at": t, "pnl": -10.0},
        {"symbol": "BTCUSDT", "closed_at": t, "pnl": 25.0},
    ]
    result = collapse_batch_closed_trades(trades)
    assert len(result) == 2
    by_symbol = {g["symbol"]: g for g in result}
    assert by_symbol["GC=F"]["pnl"] == -10.0
    assert by_symbol["BTCUSDT"]["pnl"] == 25.0


def test_collapse_batch_closed_trades_keeps_same_symbol_different_times_separate():
    """Aynı sembolün FARKLI zamanlarda kapanan bacakları (ör. günler
    arayla) KASITLI OLARAK ayrı kalmalı -- bunlar gerçekten ayrı karar
    anları, tek bir sayım artefaktı değil (DOGEUSDT örneği, Faz 398
    araştırması)."""
    t1 = datetime(2026, 8, 26, 15, 2, 23, tzinfo=UTC)
    t2 = datetime(2026, 8, 30, 22, 22, 33, tzinfo=UTC)
    trades = [
        {"symbol": "DOGEUSDT", "closed_at": t1, "pnl": -806.11},
        {"symbol": "DOGEUSDT", "closed_at": t2, "pnl": -900.48},
    ]
    result = collapse_batch_closed_trades(trades)
    assert len(result) == 2


def test_collapse_batch_closed_trades_preserves_input_order_for_first_occurrence():
    t_new = datetime(2026, 8, 30, tzinfo=UTC)
    t_old = datetime(2026, 8, 25, tzinfo=UTC)
    trades = [
        {"symbol": "BTCUSDT", "closed_at": t_new, "pnl": 5.0},
        {"symbol": "ETHUSDT", "closed_at": t_old, "pnl": -3.0},
    ]
    result = collapse_batch_closed_trades(trades)
    assert [g["symbol"] for g in result] == ["BTCUSDT", "ETHUSDT"]


def test_collapse_batch_closed_trades_handles_empty_input():
    assert collapse_batch_closed_trades([]) == []
