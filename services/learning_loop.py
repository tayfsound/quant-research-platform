"""Learning Loop — düzeltilmiş enum ve market_regime."""
from enum import Enum
from services.outcome_tracker import OutcomeTracker
from services.meta_learner import MetaLearner
from services.calibration import CalibrationMetrics
from services.agent_memory import AgentMemory
from contracts.agent_performance import AgentPerformanceRecord

class LearningLoop:
    def __init__(self):
        self.tracker = OutcomeTracker()
        self.meta_learner = MetaLearner()
        self.calibration = CalibrationMetrics()
        self.agent_memory = AgentMemory()

    def process_outcome(self, decision_id: str, pnl: float, was_correct: bool):
        from contracts.outcome import TradeOutcome
        outcome = TradeOutcome(
            pnl=pnl,
            win=pnl > 0,
            decision_correct=was_correct,
        )
        event = self.tracker.attach_outcome(decision_id, outcome)
        if not event:
            return

        self.meta_learner.record_cycle(
            confidence=event.confidence,
            was_correct=was_correct,
            reward=pnl / 100.0,
        )
        self.calibration.record(event.confidence, was_correct)

        raw = event.market_snapshot.get("raw_snapshot", {})
        regime = raw.get("trend", "")

        for opinion in event.agent_opinions:
            domain = opinion.get("domain", "unknown")
            if isinstance(domain, Enum):
                domain = domain.value
            elif isinstance(domain, dict):
                domain = domain.get("value", "unknown")

            self.agent_memory.record(AgentPerformanceRecord(
                agent_domain=str(domain),
                direction=opinion.get("direction", ""),
                confidence=opinion.get("confidence", 0.0),
                was_correct=was_correct,
                market_regime=regime,
            ))

        return event

    def get_stats(self) -> dict:
        return {
            "brier_score": self.calibration.brier_score(),
            "ece": self.calibration.expected_calibration_error(),
            "total_predictions": len(self.calibration.predictions),
            "meta_threshold": self.meta_learner.suggest_threshold(0.7),
        }
