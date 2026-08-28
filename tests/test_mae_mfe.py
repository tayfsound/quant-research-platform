"""MAE/MFE ölçüm katmanı testleri."""
from datetime import UTC, datetime, timedelta

from analytics.mae_mfe import (
    compute_competing_risk_probabilities,
    compute_conditional_mae_distribution,
    compute_confidence_decomposition,
    compute_mae_mfe,
    compute_optimal_barrier,
    compute_selection_bias_correction,
)
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


def _trade(mae_pct: float, mfe_pct: float, direction="LONG", regime="bull_trend",
           volatility_regime="normal", confidence=0.7, win=True) -> dict:
    return {
        "mae_pct": mae_pct, "mfe_pct": mfe_pct, "direction": direction,
        "regime": regime, "volatility_regime": volatility_regime,
        "confidence": confidence, "win": win,
    }


def test_conditional_distribution_computes_real_empirical_quantiles():
    """Kullanıcının kendi örneği: 50/60/70/80/90/95. yüzdelikler artan
    sırada olmalı, gerçek |MAE| değerlerinden hesaplanmalı."""
    trades = [_trade(mae_pct=-0.002 * i, mfe_pct=0.01) for i in range(1, 31)]  # -0.002..-0.06
    result = compute_conditional_mae_distribution(
        trades, group_by=("direction",), min_group_size=20,
    )
    key = "direction=LONG"
    assert key in result
    q = result[key]["mae_quantiles"]
    assert q["p50"] < q["p70"] < q["p90"] < q["p95"]
    assert result[key]["sample_size"] == 30


def test_groups_below_min_size_are_excluded_fail_closed():
    trades = [_trade(mae_pct=-0.01, mfe_pct=0.02) for _ in range(5)]
    result = compute_conditional_mae_distribution(trades, group_by=("direction",), min_group_size=20)
    assert result == {}


def test_different_regimes_produce_separate_groups():
    bull_trades = [_trade(mae_pct=-0.01, mfe_pct=0.02, regime="bull_trend") for _ in range(25)]
    bear_trades = [_trade(mae_pct=-0.05, mfe_pct=0.01, regime="bear_trend") for _ in range(25)]
    result = compute_conditional_mae_distribution(
        bull_trades + bear_trades, group_by=("regime",), min_group_size=20,
    )
    assert "regime=bull_trend" in result
    assert "regime=bear_trend" in result
    assert result["regime=bull_trend"]["mae_quantiles"]["p50"] < result["regime=bear_trend"]["mae_quantiles"]["p50"]


def test_confidence_is_automatically_bucketed():
    trades = (
        [_trade(mae_pct=-0.01, mfe_pct=0.02, confidence=0.55) for _ in range(20)]
        + [_trade(mae_pct=-0.01, mfe_pct=0.02, confidence=0.85) for _ in range(20)]
    )
    result = compute_conditional_mae_distribution(trades, group_by=("confidence",), min_group_size=20)
    assert "confidence=0.5-0.6" in result
    assert "confidence=0.8-0.9" in result


def test_trades_with_no_mae_are_skipped_without_crashing():
    trades = [{"direction": "LONG", "mae_pct": None}] * 25
    result = compute_conditional_mae_distribution(trades, group_by=("direction",), min_group_size=5)
    assert result == {}


def _outcome_trade(exit_reason: str | None, direction="LONG", regime="bull_trend",
                    volatility_regime="normal", confidence=0.7) -> dict:
    return {
        "exit_reason": exit_reason, "direction": direction, "regime": regime,
        "volatility_regime": volatility_regime, "confidence": confidence,
    }


def test_competing_risk_computes_real_empirical_probabilities():
    """Kullanıcının kendi canlı gözlemi: son 24 saatte 8 kararlı işlemin
    3'ü stop_loss, 5'i breakeven_stop — bu üçünün de gerçek sıklığını
    yansıtan bir olasılık dağılımı hesaplanmalı."""
    trades = (
        [_outcome_trade("take_profit") for _ in range(10)]
        + [_outcome_trade("stop_loss") for _ in range(6)]
        + [_outcome_trade("breakeven_stop") for _ in range(10)]
    )
    result = compute_competing_risk_probabilities(trades, group_by=("direction",), min_group_size=20)
    key = "direction=LONG"
    assert key in result
    r = result[key]
    assert r["decisive_sample_size"] == 26
    assert r["tp_count"] == 10 and r["sl_count"] == 6 and r["breakeven_stop_count"] == 10
    assert abs(r["p_take_profit"] - 10 / 26) < 1e-4
    assert abs(r["p_breakeven_stop"] - 10 / 26) < 1e-4


def test_competing_risk_excludes_censored_outcomes_from_probability():
    """manual_full/time_expired gibi yarışın sonuçlanmadığı çıkışlar
    p hesabına dahil edilmemeli — ama censored_count'ta görünmeli."""
    trades = (
        [_outcome_trade("take_profit") for _ in range(15)]
        + [_outcome_trade("stop_loss") for _ in range(10)]
        + [_outcome_trade("manual_full") for _ in range(50)]
        + [_outcome_trade("time_expired") for _ in range(50)]
    )
    result = compute_competing_risk_probabilities(trades, group_by=("direction",), min_group_size=20)
    r = result["direction=LONG"]
    assert r["decisive_sample_size"] == 25
    assert r["censored_count"] == 100
    assert abs(r["p_take_profit"] - 15 / 25) < 1e-6


def test_competing_risk_groups_below_min_size_are_excluded_fail_closed():
    trades = [_outcome_trade("take_profit") for _ in range(5)] + [_outcome_trade("stop_loss") for _ in range(5)]
    result = compute_competing_risk_probabilities(trades, group_by=("direction",), min_group_size=20)
    assert result == {}


def test_competing_risk_separates_groups_by_condition():
    bull = [_outcome_trade("take_profit", regime="bull_trend") for _ in range(20)] + [
        _outcome_trade("stop_loss", regime="bull_trend") for _ in range(5)
    ]
    bear = [_outcome_trade("stop_loss", regime="bear_trend") for _ in range(20)] + [
        _outcome_trade("take_profit", regime="bear_trend") for _ in range(5)
    ]
    result = compute_competing_risk_probabilities(bull + bear, group_by=("regime",), min_group_size=20)
    assert result["regime=bull_trend"]["p_take_profit"] > result["regime=bear_trend"]["p_take_profit"]


def _barrier_trade(mae_pct, mfe_pct, time_to_mae=100.0, time_to_mfe=50.0, direction="LONG",
                    regime="bull_trend", volatility_regime="normal", confidence=0.7) -> dict:
    return {
        "mae_pct": mae_pct, "mfe_pct": mfe_pct,
        "time_to_mae_seconds": time_to_mae, "time_to_mfe_seconds": time_to_mfe,
        "direction": direction, "regime": regime,
        "volatility_regime": volatility_regime, "confidence": confidence,
    }


def test_optimal_barrier_computes_real_ev_for_constant_trades():
    """Tüm trade'ler aynı mae/mfe/zamanlamaya sahipse yüzdelikler hep aynı
    değere düşer, tek aday çift kalır — EV hesabı (gerçek maker/taker fee
    dahil) doğru olmalı."""
    trades = [_barrier_trade(mae_pct=-0.01, mfe_pct=0.03, time_to_mae=100.0, time_to_mfe=50.0) for _ in range(30)]
    result = compute_optimal_barrier(trades, group_by=("direction",), min_group_size=20, min_decisive_count=20)
    key = "direction=LONG"
    assert key in result
    r = result[key]
    assert abs(r["sl_pct"] - 0.01) < 1e-9
    assert abs(r["tp_pct"] - 0.03) < 1e-9
    assert r["decisive_sample_size"] == 30
    assert r["decisive_fraction"] == 1.0
    expected_ev = 0.03 - 0.0005 - 0.0002
    assert abs(r["expected_value_pct"] - expected_ev) < 1e-6


def test_optimal_barrier_below_min_group_size_is_excluded():
    trades = [_barrier_trade(mae_pct=-0.01, mfe_pct=0.03) for _ in range(5)]
    result = compute_optimal_barrier(trades, group_by=("direction",), min_group_size=20)
    assert result == {}


def test_optimal_barrier_censors_trades_that_hit_neither_barrier():
    """Bazı trade'ler ne aday SL'ye ne aday TP'ye ulaşmıyorsa (ekstremumları
    çok küçük) o çift için decisive_sample_size küçülmeli — 40'ın tamamı
    asla sayılmamalı, censored olan hiç sayılmamalı (icat edilmemeli)."""
    reaching = [_barrier_trade(mae_pct=-0.02, mfe_pct=0.05) for _ in range(20)]
    barely_moving = [_barrier_trade(mae_pct=-0.001, mfe_pct=0.001) for _ in range(20)]
    result = compute_optimal_barrier(
        reaching + barely_moving, group_by=("direction",), min_group_size=20, min_decisive_count=15,
    )
    key = "direction=LONG"
    assert key in result
    assert result[key]["decisive_sample_size"] < 40


def test_optimal_barrier_separates_groups_by_regime():
    """bull: MFE'ye erken ulaşılıyor (TP kazanır) → pozitif EV, tabloya
    girer. bear: MAE'ye ÖNCE ulaşılıyor (SL kazanır) → negatif EV — iki
    grup birbirinden bağımsız hesaplanıyor ama bear_trend, negatif EV
    yüzünden SONUÇTA HİÇ GÖRÜNMÜYOR (bkz. aşağıdaki test)."""
    bull = [
        _barrier_trade(mae_pct=-0.01, mfe_pct=0.04, time_to_mae=100.0, time_to_mfe=50.0, regime="bull_trend")
        for _ in range(25)
    ]
    bear = [
        _barrier_trade(mae_pct=-0.03, mfe_pct=0.01, time_to_mae=50.0, time_to_mfe=200.0, regime="bear_trend")
        for _ in range(25)
    ]
    result = compute_optimal_barrier(bull + bear, group_by=("regime",), min_group_size=20, min_decisive_count=20)
    assert "regime=bull_trend" in result
    assert result["regime=bull_trend"]["expected_value_pct"] > 0
    assert "regime=bear_trend" not in result


def test_optimal_barrier_excludes_a_bucket_whose_best_candidate_is_still_negative_ev():
    """Kullanıcı bulgusu (2026-08-28, gerçek canlı örnek): SHORT|bear_trend
    kovalarının İKİSİNDE de ızgara taramasının bulabildiği "en iyi" (sl,tp)
    çifti bile negatif EV'liydi (-%9.7/-%8.1) — ama önceden bu, tp_pct'i
    neredeyse sıfıra yakın (%0.04) bir "öneri" olarak yine de döndürülüyordu.
    RiskTargetStage'in EV kapısı bu öneriyi kullanınca, o kovaya düşen HER
    karar (confidence %90+ dahil) yapısal olarak imkansız hale geliyordu —
    SHORT, piyasa gerçekten düşüşe geçtiğinde bile fiilen kilitleniyordu.
    Artık örneklem-eşiği kontrolüyle AYNI fail-closed ilke: en iyi bulunan
    çift bile kârlı değilse kova hiç sonuç döndürmüyor, çağıran statik
    ATR oranına düşüyor."""
    # MAE her zaman büyük, MFE her zaman küçük — hangi (sl,tp) çifti
    # denenirse denensin gerçekçi hiçbir kombinasyon kârlı çıkamaz.
    losing = [
        _barrier_trade(mae_pct=-0.15, mfe_pct=0.005, time_to_mae=50.0, time_to_mfe=200.0, regime="bear_trend")
        for _ in range(30)
    ]
    result = compute_optimal_barrier(losing, group_by=("regime",), min_group_size=20, min_decisive_count=20)
    assert "regime=bear_trend" not in result
    assert result == {}


def _decomp_trade(exit_reason: str, mfe_pct: float, confidence=0.7, direction="LONG",
                   regime="bull_trend", volatility_regime="normal") -> dict:
    return {
        "exit_reason": exit_reason, "mfe_pct": mfe_pct, "confidence": confidence,
        "direction": direction, "regime": regime, "volatility_regime": volatility_regime,
    }


def test_confidence_decomposition_matches_the_users_breakeven_stop_scenario():
    """Kullanıcının canlı gözlemi: yön doğruydu (mfe_pct pozitif) ama
    bariyer (TP mesafesi) kötü kalibreliydi — direction_probability yüksek,
    barrier_probability düşük olmalı."""
    trades = (
        [_decomp_trade("take_profit", mfe_pct=0.04) for _ in range(6)]
        + [_decomp_trade("breakeven_stop", mfe_pct=0.03) for _ in range(14)]
    )
    result = compute_confidence_decomposition(trades, group_by=("direction",), min_group_size=20)
    r = result["direction=LONG"]
    assert r["direction_probability"] == 1.0  # hepsi mfe_pct > eşik
    assert abs(r["barrier_probability"] - 6 / 20) < 1e-6  # sadece 6/20 gerçekten TP'ye ulaştı


def test_confidence_decomposition_barrier_probability_is_none_without_direction_correct_trades():
    trades = [_decomp_trade("stop_loss", mfe_pct=0.0001) for _ in range(20)]
    result = compute_confidence_decomposition(trades, group_by=("direction",), min_group_size=20)
    r = result["direction=LONG"]
    assert r["direction_probability"] == 0.0
    assert r["barrier_probability"] is None


def test_confidence_decomposition_below_min_group_size_is_excluded():
    trades = [_decomp_trade("take_profit", mfe_pct=0.02) for _ in range(5)]
    result = compute_confidence_decomposition(trades, group_by=("direction",), min_group_size=20)
    assert result == {}


def test_confidence_decomposition_ignores_censored_exits():
    trades = (
        [_decomp_trade("take_profit", mfe_pct=0.02) for _ in range(20)]
        + [_decomp_trade("manual_full", mfe_pct=0.05) for _ in range(50)]
    )
    result = compute_confidence_decomposition(trades, group_by=("direction",), min_group_size=20)
    assert result["direction=LONG"]["sample_size"] == 20


def _selection_trade(mae_pct, mfe_pct, direction="LONG", regime="bull_trend", volatility_regime="normal") -> dict:
    return {"mae_pct": mae_pct, "mfe_pct": mfe_pct, "direction": direction, "regime": regime,
            "volatility_regime": volatility_regime}


def test_selection_bias_correction_detects_that_taken_trades_are_better():
    taken = [_selection_trade(mae_pct=-0.01, mfe_pct=0.04) for _ in range(25)]
    rejected = [_selection_trade(mae_pct=-0.03, mfe_pct=0.01) for _ in range(25)]
    result = compute_selection_bias_correction(taken, rejected, group_by=("direction",), min_group_size=20)
    r = result["direction=LONG"]
    assert r["selection_adds_value"] is True
    assert r["taken_mfe_median"] > r["rejected_mfe_median"]
    assert r["taken_mae_median"] < r["rejected_mae_median"]


def test_selection_bias_correction_detects_that_selection_is_not_helping():
    """Reddedilen fırsatlar ALINAN işlemlerden daha iyi ya da eşitse,
    seçim gerçek bir değer katmıyor demektir — bu da tespit edilmeli."""
    taken = [_selection_trade(mae_pct=-0.03, mfe_pct=0.01) for _ in range(25)]
    rejected = [_selection_trade(mae_pct=-0.01, mfe_pct=0.04) for _ in range(25)]
    result = compute_selection_bias_correction(taken, rejected, group_by=("direction",), min_group_size=20)
    assert result["direction=LONG"]["selection_adds_value"] is False


def test_selection_bias_correction_requires_min_size_on_both_sides():
    taken = [_selection_trade(mae_pct=-0.01, mfe_pct=0.04) for _ in range(25)]
    rejected = [_selection_trade(mae_pct=-0.03, mfe_pct=0.01) for _ in range(5)]
    result = compute_selection_bias_correction(taken, rejected, group_by=("direction",), min_group_size=20)
    assert result == {}


def test_selection_bias_correction_separates_groups_by_regime():
    taken_bull = [_selection_trade(mae_pct=-0.01, mfe_pct=0.04, regime="bull_trend") for _ in range(20)]
    rejected_bull = [_selection_trade(mae_pct=-0.03, mfe_pct=0.01, regime="bull_trend") for _ in range(20)]
    taken_bear = [_selection_trade(mae_pct=-0.03, mfe_pct=0.01, regime="bear_trend") for _ in range(20)]
    rejected_bear = [_selection_trade(mae_pct=-0.01, mfe_pct=0.04, regime="bear_trend") for _ in range(20)]
    result = compute_selection_bias_correction(
        taken_bull + taken_bear, rejected_bull + rejected_bear, group_by=("regime",), min_group_size=20,
    )
    assert result["regime=bull_trend"]["selection_adds_value"] is True
    assert result["regime=bear_trend"]["selection_adds_value"] is False
