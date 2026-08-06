"""Learning Loop — outcome feedback + adaptive weight update."""

from enum import Enum

from contracts.agent import VOTING_AGENT_DOMAINS
from contracts.agent_performance import AgentPerformanceRecord
from contracts.decision_event import DecisionEvent
from contracts.outcome import DecisionEvaluation
from services.agent_memory import AgentMemory
from services.calibration import CalibrationMetrics
from services.weight_optimizer import WeightOptimizer
from services.weight_repository import WeightRepository


class LearningLoop:

    def __init__(self):
        self.calibration = CalibrationMetrics()
        self.agent_memory = AgentMemory()
        self.weight_repository = WeightRepository()
        self.weight_optimizer = WeightOptimizer(
            agent_memory=self.agent_memory,
            weight_repository=self.weight_repository,
        )

    def _apply_feedback(self, event, was_correct, pnl) -> None:
        self.calibration.record(
            event.confidence,
            was_correct,
        )
        raw = event.market_snapshot.get("raw_snapshot", {})
        regime = raw.get("trend", "unknown")
        for opinion in event.agent_opinions:
            domain = opinion.get("domain")
            if isinstance(domain, Enum):
                domain = domain.value
            if isinstance(domain, dict):
                domain = domain.get("value")
            # Faz 229: kritik bulgu — burası önceden domain eksik/bozuksa
            # sessizce "unknown" ajanına düşüyordu, AgentMemory'ye sahte bir
            # domain sızdırıyordu (WeightOptimizer.propose_weights() sonra
            # bu sahte domain için de anlamsız bir ağırlık öneriyordu, insan
            # onay ekranını kirletiyordu). Artık gerçek 9 oy-veren ajandan
            # biri değilse kayıt tamamen atlanıyor.
            if str(domain) not in VOTING_AGENT_DOMAINS:
                continue
            self.agent_memory.record(
                AgentPerformanceRecord(
                    agent_domain=str(domain),
                    direction=opinion.get("direction", ""),
                    confidence=opinion.get("confidence", 0.0),
                    was_correct=was_correct,
                    market_regime=regime,
                    symbol=event.symbol,
                )
            )

    def record(self, event: DecisionEvent, evaluation: DecisionEvaluation) -> None:
        outcome = evaluation.outcome
        was_correct = evaluation.was_prediction_correct
        self._apply_feedback(event, was_correct, outcome.pnl)

        from observability.metrics import learning_updates_total
        learning_updates_total.inc()

    def get_stats(self) -> dict:
        return {
            "brier_score": self.calibration.brier_score(),
            "ece": self.calibration.expected_calibration_error(),
            "total_predictions": len(self.calibration.predictions),
            "weight_domains": self.agent_memory.domains(),
        }
