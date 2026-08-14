"""Agent quality finding: SourceReliabilityAgent/ReliabilityAnnotator were
fully implemented, had their own passing tests, and were never called from
anywhere real — every agent's source_reliability stayed frozen at its own
hardcoded constant (TechnicalAgent always 0.75) forever, regardless of how
that domain's opinions actually performed over time. source_reliability is
20% of intrinsic_trust, which BeliefEngine.apply_weights() consumes via
effective_influence — so this wasn't cosmetic, it silently meant the council
never adapted trust in a domain based on its track record.

Faz 268-sonrası — kullanıcı bulgusu: bunu wire ettikten sonra bile
"reliability" hâlâ ajanın kendi bildirdiği confidence'ın ortalamasıydı
(gerçek isabet değil) ve 120 saniyede bir sıfırlanan bir in-process dict'te
tutuluyordu. Artık gerçek, kalıcı (AgentMemory) isabet oranından hesaplanıyor
— bu test artık hardcoded default'tan sapmayı DEĞİL, gerçek isabet
geçmişinin doğru şekilde yansıdığını doğruluyor."""
from contracts.agent import AgentDomain
from contracts.agent_performance import AgentPerformanceRecord
from contracts.technical import TechnicalContext
from agents.registry import AgentRegistry
from services.agent_memory import AgentMemory
from services.council_orchestrator import CouncilOrchestrator


def test_source_reliability_adapts_from_real_accuracy_not_the_agent_hardcoded_default(tmp_path):
    orchestrator = CouncilOrchestrator(AgentRegistry.create_default())
    memory = AgentMemory(storage_path=str(tmp_path))
    for _ in range(15):
        memory.record(AgentPerformanceRecord(
            agent_domain="technical", direction="LONG", confidence=0.8, was_correct=True,
        ))
    orchestrator.reliability_annotator.agent.memory = memory

    _, opinions = orchestrator.deliberate({
        AgentDomain.TECHNICAL: TechnicalContext(
            trend="bullish", momentum="strengthening", market_structure="higher_highs",
            ema_alignment="bullish_aligned", volume_confirmation=True,
            adx=30.0, di_plus=30.0, di_minus=10.0,
        ),
    })

    technical_opinion = next(o for o in opinions if o.domain == AgentDomain.TECHNICAL)
    # TechnicalAgent itself always sets source_reliability=0.75 before
    # recalculate() — this asserts the annotator actually overrode it with
    # the real, accumulated (100% correct) accuracy.
    assert technical_opinion.source_reliability != 0.75
    assert technical_opinion.source_reliability > 0.95
