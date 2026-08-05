"""Auto-bench: a domain that repeatedly shows low reliability (proxied by
low confidence, since SourceReliabilityAgent tracks confidence history) has
its vote weight genuinely zeroed out — not a "stress" metaphor, a real
performance_weight=0.0 that effective_influence (intrinsic_trust *
performance_weight) propagates into zero actual influence on the belief.
It recovers automatically once it shows real, sustained better performance."""
from contracts.agent import AgentDomain
from contracts.technical import TechnicalContext
from agents.registry import AgentRegistry
from services.council_orchestrator import CouncilOrchestrator


def test_persistently_low_confidence_domain_gets_benched_and_zeroed():
    orchestrator = CouncilOrchestrator(AgentRegistry.create_default())

    # Neutral/ranging technical context -> low-confidence opinions, repeated
    # enough times to cross BENCH_AFTER.
    weak_ctx = {AgentDomain.TECHNICAL: TechnicalContext(trend="neutral", market_structure="ranging")}
    for _ in range(6):
        orchestrator.deliberate(weak_ctx)

    _, opinions = orchestrator.deliberate(weak_ctx)
    technical = next(o for o in opinions if o.domain == AgentDomain.TECHNICAL)

    assert technical.performance_weight == 0.0
    assert technical.effective_influence == 0.0
    assert any("benched" in c.lower() for c in technical.caveats)


def test_benched_domain_recovers_after_real_strong_performance():
    orchestrator = CouncilOrchestrator(AgentRegistry.create_default())

    weak_ctx = {AgentDomain.TECHNICAL: TechnicalContext(trend="neutral", market_structure="ranging")}
    for _ in range(6):
        orchestrator.deliberate(weak_ctx)

    # Confirm it's benched first.
    _, opinions = orchestrator.deliberate(weak_ctx)
    assert next(o for o in opinions if o.domain == AgentDomain.TECHNICAL).performance_weight == 0.0

    # Real, strong, repeated signal -> high confidence -> genuine recovery.
    strong_ctx = {AgentDomain.TECHNICAL: TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs",
        ema_alignment="bullish_aligned", volume_confirmation=True,
    )}
    for _ in range(10):
        _, opinions = orchestrator.deliberate(strong_ctx)

    technical = next(o for o in opinions if o.domain == AgentDomain.TECHNICAL)
    assert technical.performance_weight == 1.0
    assert not any("benched" in c.lower() for c in technical.caveats)
