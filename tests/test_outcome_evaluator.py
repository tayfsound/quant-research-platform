"""Faz 268-sonrası — kritik bulgu (üçüncü taraf mimari incelemesi + gerçek
kod doğrulaması): r_multiple sabit $100 riskle bölünüyordu — pozisyon
büyüklüğü ne olursa olsun AYNI bölen. $1000'lik bir pozisyonda $50 kayıp
r_multiple=+0.5 (pozitif!) çıkıyordu. Artık gerçek risk miktarı
(|entry-stop|*quantity, DecisionEvent'te zaten mevcut) kullanılıyor;
o veri yoksa (fail-closed) sabit bir $ büyüklüğü uydurmak yerine sadece
yön kullanılıyor."""
from contracts.decision_event import DecisionEvent
from contracts.outcome import TradeOutcome
from services.outcome_evaluator import OutcomeEvaluator


def _event(**overrides):
    payload = {
        "symbol": "TESTUSDT",
        "final_action": "LONG",
        "confidence": 0.6,
        "entry_price": 100.0,
        "stop_loss_price": 95.0,
        "quantity": 10.0,
    }
    payload.update(overrides)
    return DecisionEvent(**payload)


def test_r_multiple_uses_real_risk_amount_not_a_fixed_100_divisor():
    """entry=100, stop=95, qty=10 -> risk_amount=50. pnl=-50 -> r=-1.0
    (eski koddaki gibi pnl/100=-0.5 DEĞİL)."""
    evaluator = OutcomeEvaluator()
    outcome = TradeOutcome(pnl=-50.0, win=False)
    result = evaluator.evaluate(_event(), outcome)
    assert result.decision_score == -1.0


def test_a_small_loss_relative_to_a_large_position_is_not_reported_as_a_win():
    """Bu, orijinal bulgunun tam senaryosu: $1000'lik pozisyonda $50
    kayıp. Eski kod (pnl/100.0) bunu +0.5 (pozitif!) raporluyordu."""
    evaluator = OutcomeEvaluator()
    # entry=100, stop=95, qty=200 -> risk_amount=1000 (büyük pozisyon).
    event = _event(quantity=200.0)
    outcome = TradeOutcome(pnl=-50.0, win=False)
    result = evaluator.evaluate(event, outcome)
    assert result.decision_score < 0
    assert result.was_prediction_correct is False


def test_r_multiple_scales_correctly_with_risk_amount():
    evaluator = OutcomeEvaluator()
    # risk_amount = |100-95|*10 = 50. pnl=+100 -> r=+2.0, 1.0'da kırpılır.
    event = _event()
    outcome = TradeOutcome(pnl=100.0, win=True)
    result = evaluator.evaluate(event, outcome)
    assert result.decision_score == 1.0

    # Aynı risk_amount, daha küçük kâr -> orantılı, kırpılmamış bir skor.
    outcome_small_win = TradeOutcome(pnl=25.0, win=True)
    result_small = evaluator.evaluate(event, outcome_small_win)
    assert result_small.decision_score == 0.5


def test_falls_back_to_direction_only_when_risk_data_is_missing():
    """entry/stop/quantity'den biri eksikse (fail-closed) sabit bir $
    büyüklük UYDURULMUYOR — sadece kazanç/kayıp yönü kullanılıyor."""
    evaluator = OutcomeEvaluator()
    event = _event(stop_loss_price=None)
    outcome = TradeOutcome(pnl=-7.0, win=False)
    result = evaluator.evaluate(event, outcome)
    assert result.decision_score == -1.0

    outcome_win = TradeOutcome(pnl=7.0, win=True)
    result_win = evaluator.evaluate(event, outcome_win)
    assert result_win.decision_score == 1.0


def test_falls_back_to_neutral_when_risk_data_missing_and_pnl_is_zero():
    evaluator = OutcomeEvaluator()
    event = _event(quantity=None)
    outcome = TradeOutcome(pnl=0.0, win=False)
    result = evaluator.evaluate(event, outcome)
    assert result.decision_score == 0.0


def test_zero_distance_stop_does_not_crash_with_division_by_zero():
    """entry == stop (risk_amount=0) -> fail-closed'a düşmeli, ZeroDivisionError değil."""
    evaluator = OutcomeEvaluator()
    event = _event(entry_price=100.0, stop_loss_price=100.0)
    outcome = TradeOutcome(pnl=-5.0, win=False)
    result = evaluator.evaluate(event, outcome)
    assert result.decision_score == -1.0
