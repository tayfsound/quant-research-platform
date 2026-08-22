"""Integration test: full cycle -> belief persist + weight snapshot chain."""
from unittest.mock import patch


def test_full_cycle_runs_finalize():
    """Tam cycle sonrasi finalize calismali."""
    # HF Hub model yuklemesini mock'la
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        from contracts.context import CognitiveCycleContext
        from contracts.outcome import TradeOutcome
        from services.cognitive_engine import CognitiveEngine

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
    from contracts.agent import AgentDomain, AgentOpinion
    from services.agent_memory import AgentMemory
    from services.weight_optimizer import WeightOptimizer

    memory = AgentMemory()
    opt = WeightOptimizer(agent_memory=memory)

    agents = [
        AgentOpinion(domain=AgentDomain.TECHNICAL, direction="LONG", confidence=0.8),
        AgentOpinion(domain=AgentDomain.MACRO, direction="LONG", confidence=0.6),
    ]

    class FakeOutcome:
        decision_score = 0.5

    weights = opt.optimize(agents, FakeOutcome(), require_approval=False)
    assert "technical" in weights
    assert "macro" in weights
    assert all(0.0 <= w <= 2.0 for w in weights.values())


def test_optimize_rewards_agreeing_agents_and_penalizes_disagreeing_ones():
    """Faz 234: kritik bulgu — canlı üretimde doğrulandı: 9 ajanın HEPSİNE
    tıpatıp aynı +0.100 verilmişti (decision_score her ajana farklılaştırma
    olmadan bloke uygulanıyordu). Nihai yönle AYNI yöndeki bir ajan
    ödüllendirilmeli, TERS yöndeki bir ajan (aynı cycle'da, aynı
    decision_score ile) CEZALANDIRILMALI — position_closer.py::
    _record_agent_learning()'in (Faz 211b) zaten uyguladığı desenin aynısı."""
    from contracts.agent import AgentDomain, AgentOpinion
    from contracts.agent_weight_snapshot import AgentWeightSnapshot
    from services.agent_memory import AgentMemory
    from services.weight_optimizer import WeightOptimizer
    from services.weight_repository import WeightRepository

    memory = AgentMemory()
    repo = WeightRepository(storage_path="test_weights_optimize_diff")
    repo.save(AgentWeightSnapshot(weights={"technical": 1.0, "macro": 1.0}).finalize())
    opt = WeightOptimizer(agent_memory=memory, weight_repository=repo)

    agents = [
        AgentOpinion(domain=AgentDomain.TECHNICAL, direction="LONG", confidence=0.8),
        AgentOpinion(domain=AgentDomain.MACRO, direction="SHORT", confidence=0.6),
    ]

    class FakeOutcome:
        decision_score = 0.5  # gerçekten kârlı bir LONG işlemi

    try:
        weights = opt.optimize(agents, FakeOutcome(), executed_direction="LONG", require_approval=False)
        # technical LONG dedi, işlem LONG ve kârlı -> ödüllendirilmeli.
        assert weights["technical"] > 1.0
        # macro SHORT dedi, işlem LONG ve kârlı -> cezalandırılmalı.
        assert weights["macro"] < 1.0
        assert weights["technical"] != weights["macro"]
    finally:
        import shutil
        shutil.rmtree("test_weights_optimize_diff", ignore_errors=True)
