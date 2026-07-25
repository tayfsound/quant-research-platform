"""Reward Signal — decision_score tabanlı."""
import math
from contracts.outcome import DecisionEvaluation

class RewardSignal:
    def __init__(self, initial_risk: float = 100.0):
        self.initial_risk = initial_risk

    def compute(self, evaluation: DecisionEvaluation) -> float:
        # Ana sinyal: decision_score
        base_reward = evaluation.decision_score

        # Güven bonusu
        confidence = evaluation.original_confidence
        if evaluation.was_prediction_correct:
            confidence_bonus = (confidence ** 2) * 0.2
        else:
            confidence_bonus = -(confidence ** 2) * 0.2

        # Öğrenme sinyali
        learning_bonus = 0.0
        if evaluation.learning_signal == "overconfident":
            learning_bonus = -0.1
        elif evaluation.learning_signal == "underconfident":
            learning_bonus = 0.05

        # Opportunity Cost
        opportunity_penalty = 0.0
        if evaluation.outcome.opportunity_cost:
            missed = evaluation.outcome.opportunity_cost.missed_r_multiple
            if missed > 0:
                opportunity_penalty = max(-0.3, -missed * 0.05)

        reward = base_reward + confidence_bonus + learning_bonus + opportunity_penalty
        return round(reward, 3)
