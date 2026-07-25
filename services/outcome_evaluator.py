"""Outcome Evaluator — sürekli Decision Score üretir."""
from contracts.outcome import TradeOutcome, DecisionEvaluation, FailureType
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType

class OutcomeEvaluator:
    def evaluate(self, ctx: CognitiveCycleContext, outcome: TradeOutcome) -> DecisionEvaluation:
        original_confidence = ctx.decision.confidence

        # Decision Score: -1 (kötü) ile +1 (iyi) arası sürekli
        if ctx.decision.action == ActionType.WAIT:
            if outcome.opportunity_cost:
                missed = outcome.opportunity_cost.missed_r_multiple
                decision_score = max(-1.0, 1.0 - missed * 0.5)
            else:
                decision_score = 0.5
        else:
            r_multiple = outcome.pnl / 100.0
            decision_score = max(-1.0, min(1.0, r_multiple))

        confidence_error = round(decision_score - original_confidence, 3)

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

    def determine_failure_type(self, ctx: CognitiveCycleContext, outcome: TradeOutcome) -> FailureType:
        if outcome.win:
            return FailureType.NONE
        if ctx.decision.confidence > 0.8 and outcome.pnl < 0:
            return FailureType.MODEL_MISCONFIDENCE
        features = ctx.market.features
        if features.get("ATR", 1) > 3:
            return FailureType.VOLATILITY_EXPANSION
        rsi = features.get("RSI", 50)
        if rsi < 30 and outcome.pnl < 0:
            return FailureType.TREND_CONTINUATION
        if rsi > 70 and outcome.pnl < 0:
            return FailureType.FALSE_REVERSAL
        return FailureType.NONE
