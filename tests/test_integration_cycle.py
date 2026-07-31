"""Integration test: full cycle -> belief persist + weight snapshot chain."""
from unittest.mock import patch, MagicMock
import pytest

def test_full_cycle_runs_finalize():
    """Tam cycle sonrasi finalize calismali."""
    # HF Hub model yuklemesini mock'la
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from services.cognitive_engine import CognitiveEngine
            from contracts.context import CognitiveCycleContext
            from contracts.outcome import TradeOutcome

            engine = CognitiveEngine()
            ctx = CognitiveCycleContext()
            ctx.market.symbol = "BTCUSDT"
            ctx.decision.proposed_direction = "LONG"
            ctx.decision.confidence = 0.8

            ctx = engine.run(ctx, persist=False)
            ctx.outcome = TradeOutcome(pnl=100, win=True, decision="LONG", confidence_at_decision=0.8)

            with patch.object(engine, "_persist_and_learn") as mock_persist:
                engine.finalize(ctx)
                mock_persist.assert_called_once()

def test_weight_optimizer_handles_pydantic_agents():
    """WeightOptimizer Pydantic AgentOpinion objelerini isleyebilmeli."""
    from services.weight_optimizer import WeightOptimizer
    from services.agent_memory import AgentMemory
    from contracts.agent import AgentOpinion, AgentDomain

    memory = AgentMemory()
    opt = WeightOptimizer(agent_memory=memory)

    agents = [
        AgentOpinion(domain=AgentDomain.TECHNICAL, direction="LONG", confidence=0.8),
        AgentOpinion(domain=AgentDomain.MACRO, direction="LONG", confidence=0.6),
    ]

    class FakeOutcome:
        decision_score = 0.5

    weights = opt.optimize(agents, FakeOutcome())
    assert "technical" in weights
    assert "macro" in weights
    assert all(0.0 <= w <= 2.0 for w in weights.values())
