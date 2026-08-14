"""Outcome Evaluator — DecisionEvent tabanlı sürekli Decision Score üretir."""

from contracts.decision_event import DecisionEvent
from contracts.outcome import DecisionEvaluation, FailureType, TradeOutcome


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
            # Faz 268-sonrası — kritik bulgu (üçüncü taraf mimari
            # incelemesi + gerçek kod doğrulaması): burası pnl'i sabit
            # $100 riskle böleniyordu — pozisyon büyüklüğü ne olursa olsun
            # AYNI bölen kullanılıyordu. $1000'lik bir pozisyonda $50
            # kayıp, r_multiple=+0.5 (POZİTİF!) çıkıyordu, tamamen yanlış.
            # Doğrusu: r_multiple = pnl / GERÇEK risk miktarı
            # (|entry-stop|*quantity, DecisionEvent'te zaten mevcut).
            # Bu üçü yoksa (fail-closed) sabit bir $ büyüklüğü UYDURMAK
            # yerine (fail-fake) sadece yönü kullanıyoruz — yanlış
            # kesinlikte bir sayı üretmek, hiç üretmemekten kötü.
            risk_amount = None
            if event.entry_price is not None and event.stop_loss_price is not None and event.quantity:
                risk_amount = abs(event.entry_price - event.stop_loss_price) * event.quantity

            if risk_amount and risk_amount > 0:
                r_multiple = outcome.pnl / risk_amount
                decision_score = max(-1.0, min(1.0, r_multiple))
            else:
                decision_score = 1.0 if outcome.win else (-1.0 if outcome.pnl < 0 else 0.0)

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
