from contracts.outcome import DecisionEvaluation, TradeOutcome
from services.reward_signal import RewardSignal


def test_reward_signal_bounds():
    rs = RewardSignal()

    evaluation = DecisionEvaluation(
        original_confidence=0.9,
        outcome=TradeOutcome(
            pnl=1000,
            win=True,
        ),
        decision_score=1.0,
        was_prediction_correct=True,
        learning_signal="confidence_well_calibrated",
    )

    reward = rs.compute(evaluation)

    assert reward <= 1.5
    assert reward > 0
