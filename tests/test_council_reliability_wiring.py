"""Agent quality finding: SourceReliabilityAgent/ReliabilityAnnotator were
fully implemented, had their own passing tests, and were never called from
anywhere real — every agent's source_reliability stayed frozen at its own
hardcoded constant (TechnicalAgent always 0.75) forever, regardless of how
that domain's opinions actually performed over time. source_reliability is
20% of intrinsic_trust, which BeliefEngine.apply_weights() consumes via
effective_influence — so this wasn't cosmetic, it silently meant the council
never adapted trust in a domain based on its track record.

Proves the real fix: after several low-confidence technical opinions, a
later technical opinion's source_reliability has moved away from the
agent's own hardcoded 0.75 default, reflecting real accumulated history."""
from contracts.agent import AgentDomain
from contracts.technical import TechnicalContext
from agents.registry import AgentRegistry
from services.council_orchestrator import CouncilOrchestrator


def test_source_reliability_adapts_from_real_history_not_the_agent_hardcoded_default():
    orchestrator = CouncilOrchestrator(AgentRegistry.create_default())

    # A run of neutral/low-signal technical contexts -> low confidence
    # opinions -> should drag technical's reliability average down.
    for _ in range(6):
        orchestrator.deliberate({
            AgentDomain.TECHNICAL: TechnicalContext(trend="neutral", market_structure="ranging"),
        })

    _, opinions = orchestrator.deliberate({
        AgentDomain.TECHNICAL: TechnicalContext(trend="neutral", market_structure="ranging"),
    })

    technical_opinion = next(o for o in opinions if o.domain == AgentDomain.TECHNICAL)
    # TechnicalAgent itself always sets source_reliability=0.75 before
    # recalculate() — this asserts the annotator actually overrode it.
    assert technical_opinion.source_reliability != 0.75
