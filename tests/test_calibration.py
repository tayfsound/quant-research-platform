"""Calibration testleri — güncellenmiş reward beklentileri."""
from contracts.outcome import DecisionEvaluation, TradeOutcome
from services.calibration import CalibrationMetrics
from services.meta_learner import MetaLearner
from services.reward_signal import RewardSignal


def test_brier_score_perfect():
    cm = CalibrationMetrics()
    cm.record(1.0, True)
    cm.record(1.0, True)
    assert cm.brier_score() == 0.0

def test_brier_score_worst():
    cm = CalibrationMetrics()
    cm.record(1.0, False)
    cm.record(1.0, False)
    assert cm.brier_score() == 1.0

def test_ece_calculation():
    cm = CalibrationMetrics()
    for _ in range(5):
        cm.record(0.9, True)
    for _ in range(5):
        cm.record(0.1, False)
    ece = cm.expected_calibration_error(n_bins=2)
    assert ece >= 0.0

def test_reliability_diagram_all_bins():
    cm = CalibrationMetrics()
    cm.record(0.55, True)
    diagram = cm.reliability_diagram(n_bins=10)
    assert len(diagram) == 10

def test_confidence_histogram():
    cm = CalibrationMetrics()
    cm.record(0.55, True)
    cm.record(0.85, False)
    hist = cm.confidence_histogram(n_bins=10)
    assert len(hist) == 10
    total = sum(h["count"] for h in hist)
    assert total == 2

def test_reward_signal_win():
    rs = RewardSignal(initial_risk=100)
    outcome = TradeOutcome(pnl=200, win=True)
    evaluation = DecisionEvaluation(
        original_confidence=0.8,
        outcome=outcome,
        decision_score=0.8,
        was_prediction_correct=True,
        learning_signal="confidence_well_calibrated",
    )
    reward = rs.compute(evaluation)
    # decision_score 0.8 + confidence bonus ~0.128 → yaklaşık 0.9+
    assert reward > 0.5

def test_reward_signal_loss_overconfident():
    rs = RewardSignal(initial_risk=100)
    outcome = TradeOutcome(pnl=-300, win=False)
    evaluation = DecisionEvaluation(
        original_confidence=0.95,
        outcome=outcome,
        decision_score=-1.0,
        was_prediction_correct=False,
        learning_signal="overconfident",
    )
    reward = rs.compute(evaluation)
    # decision_score -1.0 + ceza → negatif
    assert reward < -0.5

def test_meta_learner_suggests_parameters():
    ml = MetaLearner()
    for _ in range(30):
        ml.record_cycle(0.8, True, reward=0.5)
    for _ in range(30):
        ml.record_cycle(0.5, False, reward=-0.8)
    params = ml.suggest_parameters({"act_threshold": 0.7, "reduce_threshold": 0.4}, window=50)
    assert "act_threshold" in params
    assert "reduce_threshold" in params
    assert 0.3 <= params["act_threshold"] <= 0.9
