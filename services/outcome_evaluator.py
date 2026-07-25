"""Outcome Evaluator — DecisionEvent tabanlı sürekli Decision Score üretir."""

from contracts.decision_event import DecisionEvent
from contracts.outcome import TradeOutcome, DecisionEvaluation, FailureType


class OutcomeEvaluator:
    def evaluate(
        self,
        event: DecisionEvent,
        outcome: TradeOutcome,
    ) -> DecisionEvaluation:

        original_confidence = event.confidence

        action = event.final_action.upper()

        # Decision Score:
        # -1.0 kötü karar
        #  0.0 nötr
        # +1.0 iyi karar

        if action in ("WAIT", ""):
            if outcome.opportunity_cost:
                missed = outcome.opportunity_cost.missed_r_multiple
                decision_score = max(-1.0, 1.0 - missed * 0.5)
            else:
                decision_score = 0.5

        else:
            r_multiple = outcome.pnl / 100.0
            decision_score = max(-1.0, min(1.0, r_multiple))

        confidence_error = round(
            decision_score - original_confidence,
            3,
        )

        if original_confidence > 0.7 and decision_score < 0:
            learning_signal = "overconfident"

        elif original_confidence < 0.4 and decision_score > 0:
            learning_signal = "underconfident"

        else:
            learning_signal = "confidence_well_calibrated"

        return DecisionEvaluation(
            original_confidence=original_confidence,
            outcome=outcome,
            confidence_error=confidence_error,
            decision_score=round(decision_score, 3),
            was_prediction_correct=decision_score > 0,
            learning_signal=learning_signal,
        )


    def determine_failure_type(
        self,
        event: DecisionEvent,
        outcome: TradeOutcome,
    ) -> FailureType:

        if outcome.win:
            return FailureType.NONE

        if event.confidence > 0.8 and outcome.pnl < 0:
            return FailureType.MODEL_MISCONFIDENCE

        features = event.market_snapshot.get("features", {})

        if features.get("ATR", 1) > 3:
            return FailureType.VOLATILITY_EXPANSION

        rsi = features.get("RSI", 50)

        if rsi < 30 and outcome.pnl < 0:
            return FailureType.TREND_CONTINUATION

        if rsi > 70 and outcome.pnl < 0:
            return FailureType.FALSE_REVERSAL

        return FailureType.NONE
