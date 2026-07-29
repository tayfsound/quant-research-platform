"""Outcome feedback loop testleri."""

import shutil
from uuid import uuid4

from contracts.decision_event import DecisionEvent
from contracts.outcome import TradeOutcome, DecisionEvaluation
from contracts.agent_weight_snapshot import AgentWeightSnapshot
from database.connection import get_session
from services.decision_persistor import DecisionPersistor
from services.outcome_evaluator import OutcomeEvaluator
from services.weight_optimizer import WeightOptimizer
from services.agent_memory import AgentMemory
from services.weight_repository import WeightRepository


def test_outcome_evaluates_pnl():
    event = DecisionEvent(
        symbol="BTCUSDT",
        confidence=0.7,
        final_action="ENTER_LONG",
    )
    outcome = TradeOutcome(pnl=150.0, win=True)
    evaluator = OutcomeEvaluator()
    evaluation = evaluator.evaluate(event, outcome)

    assert evaluation.outcome.pnl == 150.0
    assert evaluation.decision_score > 0


def test_weight_update_is_gradual():
    memory = AgentMemory()
    repo = WeightRepository(storage_path="test_feedback_weights")

    current = AgentWeightSnapshot(
        weights={"technical": 0.5},
        reason="seed",
    ).finalize()
    repo.save(current)

    optimizer = WeightOptimizer(memory, weight_repository=repo)
    agents = [{"domain": "technical", "confidence": 0.8}]
    evaluation = DecisionEvaluation(
        original_confidence=0.7,
        outcome=TradeOutcome(pnl=200.0, win=True),
        decision_score=1.0,
        was_prediction_correct=True,
    )

    new_weights = optimizer.optimize(agents=agents, outcome=evaluation)

    # 0.5 -> istenen ~0.7, ancak delta 0.10 ile kırpılır
    assert new_weights["technical"] == 0.6

    shutil.rmtree("test_feedback_weights", ignore_errors=True)


def test_decision_persisted_to_db():
    event = DecisionEvent(
        id=uuid4(),
        symbol="BTCUSDT",
        proposed_direction="LONG",
        final_action="ENTER_LONG",
        final_size=0.5,
        confidence=0.75,
        agent_opinions=[{"domain": "technical", "confidence": 0.8}],
        risk_evaluation={"verdict": "approved"},
    )

    session = get_session()
    persistor = DecisionPersistor(session)
    persistor.persist(event)

    rows = persistor.get_by_symbol("BTCUSDT", limit=10)
    assert len(rows) >= 1
    assert rows[0]["symbol"] == "BTCUSDT"
    assert rows[0]["direction"] == "LONG"
