"""Auto-bench: a domain with a genuinely poor REAL track record (was_correct-
based, from AgentMemory — not raw confidence, bkz. agents/source_
reliability_agent.py) has its vote weight genuinely zeroed out — not a
"stress" metaphor, a real performance_weight=0.0 that effective_influence
(intrinsic_trust * performance_weight) propagates into zero actual
influence on the belief. It recovers once it shows real, sustained
better accuracy."""
from agents.registry import AgentRegistry
from contracts.agent import AgentDomain
from contracts.agent_performance import AgentPerformanceRecord
from contracts.technical import TechnicalContext
from services.agent_memory import AgentMemory
from services.council_orchestrator import CouncilOrchestrator


def _seed(memory: AgentMemory, domain: str, n: int, was_correct: bool) -> None:
    for _ in range(n):
        memory.record(AgentPerformanceRecord(
            agent_domain=domain, direction="LONG", confidence=0.8, was_correct=was_correct,
        ))


def test_persistently_wrong_domain_gets_benched_and_zeroed(tmp_path):
    orchestrator = CouncilOrchestrator(AgentRegistry.create_default())
    memory = AgentMemory(storage_path=str(tmp_path))
    _seed(memory, "technical", 15, was_correct=False)
    orchestrator.reliability_annotator.agent.memory = memory

    ctx = {AgentDomain.TECHNICAL: TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs",
        ema_alignment="bullish_aligned", volume_confirmation=True,
        adx=30.0, di_plus=30.0, di_minus=10.0,
    )}
    _, opinions = orchestrator.deliberate(ctx)
    technical = next(o for o in opinions if o.domain == AgentDomain.TECHNICAL)

    assert technical.performance_weight == 0.0
    assert technical.effective_influence == 0.0
    assert any("benched" in c.lower() for c in technical.caveats)


def test_benched_domain_recovers_after_real_correct_track_record(tmp_path):
    orchestrator = CouncilOrchestrator(AgentRegistry.create_default())
    memory = AgentMemory(storage_path=str(tmp_path))
    _seed(memory, "technical", 15, was_correct=False)
    orchestrator.reliability_annotator.agent.memory = memory

    ctx = {AgentDomain.TECHNICAL: TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs",
        ema_alignment="bullish_aligned", volume_confirmation=True,
        adx=30.0, di_plus=30.0, di_minus=10.0,
    )}
    _, opinions = orchestrator.deliberate(ctx)
    assert next(o for o in opinions if o.domain == AgentDomain.TECHNICAL).performance_weight == 0.0

    # Gerçek, sürekli isabetli sonuçlar birikince — genuine recovery.
    _seed(memory, "technical", 20, was_correct=True)
    _, opinions = orchestrator.deliberate(ctx)

    technical = next(o for o in opinions if o.domain == AgentDomain.TECHNICAL)
    assert technical.performance_weight == 1.0
    assert not any("benched" in c.lower() for c in technical.caveats)


def test_insufficient_real_history_is_not_benched(tmp_path):
    """Yeni bir domain'in (henüz gerçek kapanmış işlem geçmişi olmayan)
    fail-closed davranışı: nötr, tam ağırlık — cezalandırılmıyor."""
    orchestrator = CouncilOrchestrator(AgentRegistry.create_default())
    orchestrator.reliability_annotator.agent.memory = AgentMemory(storage_path=str(tmp_path))

    ctx = {AgentDomain.TECHNICAL: TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs",
        ema_alignment="bullish_aligned", volume_confirmation=True,
        adx=30.0, di_plus=30.0, di_minus=10.0,
    )}
    _, opinions = orchestrator.deliberate(ctx)
    technical = next(o for o in opinions if o.domain == AgentDomain.TECHNICAL)

    assert technical.performance_weight == 1.0
    assert not any("benched" in c.lower() for c in technical.caveats)
