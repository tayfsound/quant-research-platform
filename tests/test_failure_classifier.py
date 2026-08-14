"""Faz 268-sonrası — kullanıcının kendi getirdiği çerçeve: her SL işlemini
GERÇEK MAE/MFE verisine göre direction_error/barrier_error diye ayırma."""
from analytics.failure_classifier import classify_stop_loss_failure, summarize_stop_loss_failures


def test_scenario_a_bad_prediction_is_direction_error():
    """Kullanıcının Senaryo A'sı: MFE küçük, fiyat hiç lehimize gitmedi."""
    result = classify_stop_loss_failure(
        entry_price=100.0, stop_loss_price=99.0, take_profit_price=102.0,
        mae_pct=-0.015, mfe_pct=0.008,
    )
    assert result == "direction_error"


def test_scenario_b_stop_too_tight_is_barrier_error():
    """Kullanıcının Senaryo B'si: MFE hedefe çok yakın/üstünde ama stop
    dar olduğu için işlem yine de kaybetti — model hatası değil."""
    result = classify_stop_loss_failure(
        entry_price=100.0, stop_loss_price=99.0, take_profit_price=102.0,
        mae_pct=-0.0105, mfe_pct=0.018,
    )
    assert result == "barrier_error"


def test_scenario_c_deep_adverse_move_with_tiny_mfe_is_direction_error():
    result = classify_stop_loss_failure(
        entry_price=100.0, stop_loss_price=99.0, take_profit_price=102.0,
        mae_pct=-0.017, mfe_pct=0.003,
    )
    assert result == "direction_error"


def test_missing_data_is_insufficient_data_not_a_fabricated_category():
    assert classify_stop_loss_failure(None, 99.0, 102.0, -0.01, 0.01) == "insufficient_data"
    assert classify_stop_loss_failure(100.0, 99.0, 102.0, None, 0.01) == "insufficient_data"
    assert classify_stop_loss_failure(100.0, 99.0, 102.0, -0.01, None) == "insufficient_data"
    assert classify_stop_loss_failure(100.0, 99.0, None, -0.01, 0.01) == "insufficient_data"


def test_reachability_exactly_at_threshold_is_barrier_error():
    # planned_target_pct = 0.02, mfe_pct = 0.014 -> reachability tam 0.7.
    result = classify_stop_loss_failure(
        entry_price=100.0, stop_loss_price=99.0, take_profit_price=102.0,
        mae_pct=-0.01, mfe_pct=0.014,
    )
    assert result == "barrier_error"


def test_summarize_stop_loss_failures_returns_real_shape():
    result = summarize_stop_loss_failures(hours=90)
    assert "total_stop_loss_trades" in result
    assert result["direction_error_count"] + result["barrier_error_count"] + result["insufficient_data_count"] == result["total_stop_loss_trades"]
    if result["total_stop_loss_trades"] > 0:
        assert 0.0 <= (result["direction_error_pct"] or 0.0) <= 1.0
