import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
src = REPO / "services" / "learning_loop.py"
bak = REPO / "services" / "learning_loop.py.bak"

# Yedekle
import shutil
shutil.copy2(src, bak)
print("yedek: learning_loop.py.bak")

src.write_text('''"""Learning Loop — outcome feedback + adaptive weight update."""

from enum import Enum

from contracts.agent_performance import AgentPerformanceRecord
from contracts.decision_event import DecisionEvent
from contracts.outcome import DecisionEvaluation
from services.agent_memory import AgentMemory
from services.calibration import CalibrationMetrics
from services.meta_learner import MetaLearner
from services.outcome_tracker import OutcomeTracker
from services.weight_optimizer import WeightOptimizer
from services.weight_repository import WeightRepository


class LearningLoop:

    def __init__(self):
        self.tracker = OutcomeTracker()
        self.meta_learner = MetaLearner()
        self.calibration = CalibrationMetrics()
        self.agent_memory = AgentMemory()
        self.weight_repository = WeightRepository()
        self.weight_optimizer = WeightOptimizer(
            agent_memory=self.agent_memory,
            weight_repository=self.weight_repository,
        )

    def _apply_feedback(self, event, was_correct, pnl) -> None:
        reward = pnl / 100.0
        self.meta_learner.record_cycle(
            confidence=event.confidence,
            was_correct=was_correct,
            reward=reward,
        )
        self.calibration.record(
            event.confidence,
            was_correct,
        )
        raw = event.market_snapshot.get("raw_snapshot", {})
        regime = raw.get("trend", "unknown")
        for opinion in event.agent_opinions:
            domain = opinion.get("domain", "unknown")
            if isinstance(domain, Enum):
                domain = domain.value
            if isinstance(domain, dict):
                domain = domain.get("value", "unknown")
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

    def process_outcome(self, decision_id: str, pnl: float, was_correct: bool):
        from contracts.outcome import TradeOutcome
        outcome = TradeOutcome(
            pnl=pnl,
            win=pnl > 0,
            decision_correct=was_correct,
        )
        event = self.tracker.attach_outcome(decision_id, outcome)
        if not event:
            return None
        self._apply_feedback(event, was_correct, pnl)
        if len(self.agent_memory.domains()) > 0:
            self.weight_optimizer.propose_weights(evaluation_window=100)
        return event

    def record(self, event: DecisionEvent, evaluation: DecisionEvaluation) -> None:
        outcome = evaluation.outcome
        was_correct = evaluation.was_prediction_correct
        self._apply_feedback(event, was_correct, outcome.pnl)

    def get_stats(self) -> dict:
        return {
            "brier_score": self.calibration.brier_score(),
            "ece": self.calibration.expected_calibration_error(),
            "total_predictions": len(self.calibration.predictions),
            "meta_threshold": self.meta_learner.suggest_threshold(0.7),
            "weight_domains": self.agent_memory.domains(),
        }
''')
print("learning_loop.py DRY refactor")

r = subprocess.run(["pytest", "-q", "--ignore=tests/test_ml.py"], cwd=REPO)
if r.returncode != 0:
    shutil.copy2(bak, src)
    bak.unlink()
    print("[FAIL] Tests red — geri alındı", file=sys.stderr)
    sys.exit(1)

bak.unlink()
subprocess.run(["git", "add", "-A"], cwd=REPO, check=True)
subprocess.run(["git", "commit", "-m", "refactor: learning_loop DRY — _apply_feedback extract"], cwd=REPO, check=True)
subprocess.run(["git", "push", "origin", "main"], cwd=REPO, check=True)
print("[OK] Done")
