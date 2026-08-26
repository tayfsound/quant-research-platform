"""Faz 352 — Regime Reversal Guardian, saf hesaplama testleri."""
from analytics.regime_reversal import consecutive_stop_streak


def _trade(exit_reason: str) -> dict:
    return {"outcome": {"exit_reason": exit_reason}}


def test_all_stop_losses_counts_full_length():
    trades = [_trade("stop_loss") for _ in range(5)]
    assert consecutive_stop_streak(trades) == 5


def test_streak_stops_at_first_non_stop_loss_going_backward():
    trades = [_trade("stop_loss"), _trade("stop_loss"), _trade("take_profit"), _trade("stop_loss")]
    assert consecutive_stop_streak(trades) == 2


def test_non_stop_loss_first_trade_returns_zero():
    trades = [_trade("take_profit"), _trade("stop_loss"), _trade("stop_loss")]
    assert consecutive_stop_streak(trades) == 0


def test_empty_list_returns_zero():
    assert consecutive_stop_streak([]) == 0


def test_missing_outcome_or_exit_reason_treated_as_non_stop():
    trades = [{"outcome": None}, _trade("stop_loss")]
    assert consecutive_stop_streak(trades) == 0

    trades2 = [{}, _trade("stop_loss")]
    assert consecutive_stop_streak(trades2) == 0


def test_liquidation_counts_as_a_loss_and_does_not_break_the_streak():
    """Faz 363 — kritik bulgu, canlıda yakalandı (2026-08-26): streak
    hesabı ÖNCEDEN SADECE 'stop_loss'ı sayıyordu — bir 'liquidation'
    (stop_loss'tan bile daha büyük, kontrolsüz bir kayıp) streak'i
    kırıp ONDAN ÖNCEKİ (daha eski) ardışık stop_loss'ları bile
    saymadan durduruyordu. Gerçek olay: son 20 LONG kapanışının TAMAMI
    kayıptı (stop_loss+liquidation karışık) ama eski kod sadece 6
    buluyordu (7. sıradaki liquidation streak'i kesiyordu) —
    regime_reversal_guardian'ın eşiği (10) hiç aşılmadı, koruma hiç
    tetiklenmedi. Artık liquidation da 'gerçek kayıp' sayılıyor."""
    trades = [
        _trade("stop_loss"), _trade("stop_loss"), _trade("liquidation"),
        _trade("stop_loss"), _trade("stop_loss"), _trade("stop_loss"),
    ]
    assert consecutive_stop_streak(trades) == 6


def test_breakeven_stop_and_reduced_loss_stop_also_count_as_losses():
    """analytics/failure_classifier.py::LOSS_EXIT_REASONS ile AYNI, tutarlı
    tanım — bu iki exit_reason da 'gerçek kayıp' kategorisinde."""
    trades = [_trade("breakeven_stop"), _trade("reduced_loss_stop"), _trade("stop_loss")]
    assert consecutive_stop_streak(trades) == 3


def test_manual_and_time_expired_still_break_the_streak():
    """Kasıtlı/planlı çıkışlar (manuel kapatma, süre dolumu) HÂLÂ bir
    rejim-değişimi sinyali sayılmıyor — sadece kontrolsüz/gerçek kayıp
    kategorileri sayılıyor, bu ayrım BİLEREK korunuyor."""
    trades = [_trade("stop_loss"), _trade("manual_full"), _trade("stop_loss")]
    assert consecutive_stop_streak(trades) == 1

    trades2 = [_trade("stop_loss"), _trade("time_expired"), _trade("stop_loss")]
    assert consecutive_stop_streak(trades2) == 1
